from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from rich.panel import Panel
import pika, json, threading, time
from collections import deque

RABBIT_HOST = "localhost"

promos = deque(maxlen=10)
payments = deque(maxlen=10)
logs = deque(maxlen=5)

def add_log(msg):
    logs.appendleft(msg)

class PromoWidget(Static):
    def render(self):
        return Panel("\n".join(list(promos)), title="📢 Promoções")

class PaymentWidget(Static):
    def render(self):
        return Panel("\n".join(list(payments)), title="💳 Pagamentos")

class LogWidget(Static):
    def render(self):
        return Panel("\n".join(list(logs)), title="📘 Logs")

class ReservationInput(Input):
    placeholder = "reservar ITN001 2 1"

class CruiseDashboard(App):
    CSS_PATH = None
    BINDINGS = [("q", "quit", "Sair")]

    promo: PromoWidget
    payment: PaymentWidget
    logs_panel: LogWidget
    input_box: ReservationInput

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            with Horizontal():
                self.promo = PromoWidget()
                self.payment = PaymentWidget()
                self.logs_panel = LogWidget()
                yield self.promo
                yield self.payment
                yield self.logs_panel
            self.input_box = ReservationInput()
            yield self.input_box
        yield Footer()

    def on_mount(self):
        self.set_interval(1, self.refresh_views)
        threading.Thread(target=self.consume_promotions, daemon=True).start()
        threading.Thread(target=self.consume_payments, daemon=True).start()

    def refresh_views(self):
        self.promo.refresh()
        self.payment.refresh()
        self.logs_panel.refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        self.input_box.value = ""
        if cmd.startswith("reservar"):
            try:
                _, itin, p, c = cmd.split()
                self.send_reservation(itin, int(p), int(c))
            except:
                add_log("❗ Uso: reservar <ITINERARIO> <PESSOAS> <CABINES>")
        else:
            add_log("❗ Comando desconhecido")

    def consume_promotions(self):
        for dest in ["Salvador", "Rio de Janeiro", "Minas Gerais"]:
            def run(dest=dest):
                try:
                    conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
                    ch = conn.channel()
                    ch.queue_declare(queue=f"promocoes-{dest}")
                    for _, _, body in ch.consume(queue=f"promocoes-{dest}", auto_ack=True):
                        msg = "Minas não tem mar, bobo(a)!" if dest == "Minas Gerais" else body.decode()
                        promos.appendleft(f"{dest}: {msg}")
                except:
                    promos.appendleft(f"[Erro] Falha nas promoções de {dest}")
            threading.Thread(target=run, daemon=True).start()

    def consume_payments(self):
        def run(queue, status):
            try:
                conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
                ch = conn.channel()
                ch.queue_declare(queue=queue)
                for _, _, body in ch.consume(queue=queue, auto_ack=True):
                    data = json.loads(body)
                    res_id = data["data"]["reserva_id"]
                    payments.appendleft(f"{res_id} {status}")
                    add_log(f"{'✅' if status == 'Aprovado' else '❌'} Pagamento: {res_id}")
            except:
                add_log(f"[Erro] Falha em {queue}")
        threading.Thread(target=run, args=("pagamento-aprovado", "Aprovado"), daemon=True).start()
        threading.Thread(target=run, args=("pagamento-recusado", "Recusado"), daemon=True).start()

    def send_reservation(self, itinerary_id, passengers, cabins):
        try:
            conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
            ch = conn.channel()
            ch.queue_declare(queue="reserva-criada")
            res_id = str(int(time.time() * 1000))
            payload = {
                "reserva_id": res_id,
                "itinerario_id": itinerary_id,
                "passageiros": passengers,
                "cabines": cabins
            }
            ch.basic_publish(exchange='', routing_key="reserva-criada", body=json.dumps(payload))
            add_log(f"📤 Reserva enviada: {res_id}")
        except Exception as e:
            add_log(f"❗ Erro ao reservar: {e}")

if __name__ == "__main__":
    CruiseDashboard().run()
