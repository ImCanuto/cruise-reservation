from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input
from rich.panel import Panel
import pika, json, threading, time
from collections import deque

RABBIT_HOST = "localhost"

# estado global
data = {
    'reservas': {},       # reserva_id → {'payment': 'Aprovado'/'Recusado'/None, 'ticket': (id,destino)/None}
    'promos': deque(maxlen=10)
}
logs = deque(maxlen=20)

def add_log(msg):
    logs.appendleft(msg)

class ListWidget(Static):
    def __init__(self, getter, title, **kw):
        super().__init__(**kw)
        self.getter = getter
        self.title = title
    def render(self):
        items = self.getter() or ["(vazio)"]
        return Panel("\n".join(items), title=self.title)

class PromoWidget(ListWidget):
    def __init__(self): super().__init__(lambda: list(data['promos']), "📢 Promoções")

class PaymentWidget(ListWidget):
    def __init__(self):
        def payments():
            return [f"{rid}: {info['payment']}"
                    for rid, info in data['reservas'].items()
                    if info['payment'] is not None]
        super().__init__(payments, "💳 Pagamentos")

class TicketWidget(ListWidget):
    def __init__(self):
        def tickets():
            return [f"{rid}: {tid} ({destino})"
                    for rid, info in data['reservas'].items()
                    if info['ticket'] is not None
                    for tid, destino in [info['ticket']]]
        super().__init__(tickets, "🎟️ Bilhetes")

class LogWidget(ListWidget):
    def __init__(self): super().__init__(lambda: list(logs), "📘 Logs")

class ReservationInput(Input):
    placeholder = "reservar ITN001 2 1"

class CruiseDashboard(App):
    CSS_PATH = None
    BINDINGS = [("q", "quit", "Sair")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield PromoWidget()
        yield PaymentWidget()
        yield TicketWidget()
        yield LogWidget()
        yield ReservationInput()
        yield Footer()

    def on_mount(self):
        # refresca toda tela a cada 1s
        self.set_interval(1, lambda: [w.refresh() for w in self.query(ListWidget)])
        # threads de consumo
        threading.Thread(target=self.consume_promotions, daemon=True).start()
        threading.Thread(target=self.consume_payments, daemon=True).start()
        threading.Thread(target=self.consume_tickets, daemon=True).start()

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

    def consume_promotions(self):
        for dest in ["Salvador","Rio de Janeiro","Minas Gerais"]:
            def run(d=dest):
                try:
                    conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
                    ch = conn.channel()
                    ch.queue_declare(queue=f"promocoes-{d}")
                    for _,_,body in ch.consume(queue=f"promocoes-{d}", auto_ack=True):
                        data['promos'].appendleft(body.decode())
                except:
                    data['promos'].appendleft(f"[ERRO promo] {d}")
            threading.Thread(target=run, daemon=True).start()

    def consume_payments(self):
        def run(status):
            try:
                conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
                ch = conn.channel()
                # bind em exchange 'pagamento'
                ch.exchange_declare(exchange='pagamento', exchange_type='direct')
                q = ch.queue_declare(queue='', exclusive=True).method.queue
                ch.queue_bind(exchange='pagamento', queue=q, routing_key=f'pagamento-{status}')
                for _,_,body in ch.consume(queue=q, auto_ack=True):
                    env = json.loads(body)
                    rid = env['data']['reserva_id']
                    data['reservas'].setdefault(rid, {'payment':None,'ticket':None})
                    data['reservas'][rid]['payment'] = status.capitalize()
                    add_log(f"{'✅' if status=='aprovado' else '❌'} Pagamento: {rid}")
            except Exception as e:
                add_log(f"[ERRO pagamento] {e}")
        threading.Thread(target=run, args=("aprovado",), daemon=True).start()
        threading.Thread(target=run, args=("recusado",), daemon=True).start()

    def consume_tickets(self):
        try:
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

    def send_reservation(self, itin, pax, cab):
        try:
            rid = str(int(time.time()*1000))
            data['reservas'][rid] = {'payment':None,'ticket':None}
            payload = {"reserva_id":rid,"itinerario_id":itin,"passageiros":pax,"cabines":cab}
            conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
            ch = conn.channel()
            ch.queue_declare(queue="reserva-criada")
            ch.basic_publish(exchange='', routing_key="reserva-criada", body=json.dumps(payload))
            add_log(f"📤 Reserva enviada: {rid}")
        except Exception as e:
            add_log(f"[ERRO reservar] {e}")

if __name__ == "__main__":
    CruiseDashboard().run()
