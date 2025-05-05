from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input
from rich.panel import Panel
import pika, json, threading, time
from collections import deque

RABBIT_HOST = "localhost" # era do docker

# estado global
# guarda o estado atual da aplicação: reservas e promoções recebidas
data = {
    'reservas': {},       # reserva_id → {'payment': 'Aprovado'/'Recusado'/None, 'ticket': (id,destino)/None}
    'promos': deque(maxlen=10)
}
# mantém uma lista dos últimos eventos ou mensagens do sistema
logs = deque(maxlen=20)
# carrega a chave pública do serviço de pagamento, usada para verificar assinaturas
with open("keys/pagamento_public.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read())

# função para adicionar uma nova mensagem ao log
def add_log(msg):
    logs.appendleft(msg)

# classe base para exibir listas (de promoções, pagamentos, etc) na interface
class ListWidget(Static):
    def __init__(self, getter, title, **kw):
        super().__init__(**kw)
        self.getter = getter
        self.title = title
    def render(self):
        items = self.getter() or ["(vazio)"]
        return Panel("\n".join(items), title=self.title)

# widget que mostra a lista de promoções recebidas
class PromoWidget(ListWidget):
    def __init__(self): super().__init__(lambda: list(data['promos']), "📢 Promoções")

# widget que mostra o status dos pagamentos das reservas
class PaymentWidget(ListWidget):
    def __init__(self):
        def payments():
            return [f"{rid}: {info['payment']}"
                    for rid, info in data['reservas'].items()
                    if info['payment'] is not None]
        super().__init__(payments, "💳 Pagamentos")

# widget que mostra os bilhetes gerados para as reservas
class TicketWidget(ListWidget):
    def __init__(self):
        def tickets():
            return [f"{rid}: {tid} ({destino})"
                    for rid, info in data['reservas'].items()
                    if info['ticket'] is not None
                    for tid, destino in [info['ticket']]]
        super().__init__(tickets, "🎟️ Bilhetes")

# widget que mostra o log de eventos recentes
class LogWidget(ListWidget):
    def __init__(self): super().__init__(lambda: list(logs), "📘 Logs")

# campo de texto onde o usuário digita comandos de reserva
class ReservationInput(Input):
    placeholder = "reservar ITN001 2 1"

# classe principal da aplicação visual em terminal
class CruiseDashboard(App):
    CSS_PATH = None
    BINDINGS = [("q", "quit", "Sair")]

# define os elementos visuais que compõem a tela principal
    def compose(self) -> ComposeResult:
        yield Header()
        yield PromoWidget()
        yield PaymentWidget()
        yield TicketWidget()
        yield LogWidget()
        yield ReservationInput()
        yield Footer()

# executado quando a interface inicia; configura atualizações e threads
    def on_mount(self):
        # refresca toda tela a cada 1s
        self.set_interval(1, lambda: [w.refresh() for w in self.query(ListWidget)])
        # threads de consumo
        threading.Thread(target=self.consume_promotions, daemon=True).start()
        threading.Thread(target=self.consume_payments, daemon=True).start()
        threading.Thread(target=self.consume_tickets, daemon=True).start()

# interpreta o comando digitado no campo de texto
    def on_input_submitted(self, event):
        cmd = event.value.strip()
        event.input.value = ""
        if cmd.startswith("reservar"):
            try:
                _, itin, p, c = cmd.split()
                self.send_reservation(itin, int(p), int(c))
            except:
                add_log("❗ Uso: reservar <ITINERARIO> <PESSOAS> <CABINES>")
        else:
            add_log("❗ Comando desconhecido")

# cria uma thread para cada destino, ouvindo promoções que chegam do RabbitMQ
    def consume_promotions(self):
        for dest in ["Salvador","Rio de Janeiro","Minas Gerais"]:
            def run(d=dest):
                try:
                    # conexão e canal para cada destino
# define o endereço do servidor RabbitMQ
                    conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
                    ch = conn.channel()
                    ch.queue_declare(queue=f"promocoes-{d}")
                    for _,_,body in ch.consume(queue=f"promocoes-{d}", auto_ack=True):
                        data['promos'].appendleft(body.decode())
                except:
                    data['promos'].appendleft(f"[ERRO promo] {d}")
            threading.Thread(target=run, daemon=True).start()

# escuta os pagamentos (aprovado/recusado), verifica assinatura e atualiza o estado
    def consume_payments(self):
        def run(status):
            try:
# define o endereço do servidor RabbitMQ
                conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
                ch = conn.channel()
                ch.exchange_declare(exchange='pagamento', exchange_type='direct')
                q = ch.queue_declare(queue='', exclusive=True).method.queue
                ch.queue_bind(exchange='pagamento', queue=q, routing_key=f'pagamento-{status}')
                for _, _, body in ch.consume(queue=q, auto_ack=True):
                    envelope = json.loads(body)
                    data_msg = envelope['data']
                    signature = bytes.fromhex(envelope['signature'])
                    rid = data_msg['reserva_id']

                    try:
                        # verifica a assinatura
                        public_key.verify(
                            signature,
                            json.dumps(data_msg, sort_keys=True).encode(),
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                            hashes.SHA256()
                        )
                        data['reservas'].setdefault(rid, {'payment': None, 'ticket': None})
                        data['reservas'][rid]['payment'] = status.capitalize()
                        icon = '✅' if status == 'aprovado' else '❌'
                        add_log(f"{icon} Pagamento ({status}): {rid}")
                    except Exception as e:
                        add_log(f"⚠️ Assinatura inválida para {rid}: {e}")
            except Exception as e:
                add_log(f"[ERRO pagamento] {e}")
        threading.Thread(target=run, args=("aprovado",), daemon=True).start()
        threading.Thread(target=run, args=("recusado",), daemon=True).start()

# escuta a fila de bilhetes e atualiza o painel com bilhetes gerados
    def consume_tickets(self):
        try:
# define o endereço do servidor RabbitMQ
            conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
            ch = conn.channel()
            ch.queue_declare(queue="bilhete-gerado")
            for _,_,body in ch.consume(queue="bilhete-gerado", auto_ack=True):
                info = json.loads(body)
                rid = info['reserva_id']
                tid = info['bilhete_id']
                dest = info.get('destino','')
                data['reservas'].setdefault(rid, {'payment':None,'ticket':None})
                data['reservas'][rid]['ticket'] = (tid, dest)
                add_log(f"🎟️ Bilhete gerado: {tid} para {rid}")
        except Exception as e:
            add_log(f"[ERRO bilhete] {e}")

# Envia uma nova reserva para a fila 'reserva-criada'
    def send_reservation(self, itin, pax, cab):
        try:
            rid = str(int(time.time()*1000))
            data['reservas'][rid] = {'payment':None,'ticket':None}
            payload = {"reserva_id":rid,"itinerario_id":itin,"passageiros":pax,"cabines":cab}
# define o endereço do servidor RabbitMQ
            conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
            ch = conn.channel()
            ch.queue_declare(queue="reserva-criada")
            ch.basic_publish(exchange='', routing_key="reserva-criada", body=json.dumps(payload))
            add_log(f"📤 Reserva enviada: {rid}")
        except Exception as e:
            add_log(f"[ERRO reservar] {e}")

# ponto de entrada do programa: inicia o dashboard
if __name__ == "__main__":
    CruiseDashboard().run()
