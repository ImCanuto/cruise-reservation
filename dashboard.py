# dashboard.py

import threading
import json
import os
import time
from collections import deque
from uuid import uuid4

import pika
from rich.live import Live
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from prompt_toolkit import PromptSession

# Configuração do RabbitMQ
RABBIT_HOST = os.getenv("RABBIT_HOST", "localhost")

# Buffers para exibir no dashboard
promos   = deque(maxlen=10)
payments = deque(maxlen=10)
tickets  = deque(maxlen=10)
logs     = deque(maxlen=5)

def log(msg):
    logs.appendleft(msg)

def start_promotions_consumers():
    destinations = ["Salvador", "Rio de Janeiro", "Minas Gerais"]
    for dest in destinations:
        def run(dest=dest):
            conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
            ch = conn.channel()
            qn = f"promocoes-{dest}"
            ch.queue_declare(queue=qn)
            for _, _, body in ch.consume(queue=qn, auto_ack=True):
                promos.appendleft(f"{dest}: {body.decode()}")
        threading.Thread(target=run, daemon=True).start()

def start_payment_consumers():
    def run(queue_name, status_text):
        conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
        ch = conn.channel()
        ch.queue_declare(queue=queue_name)
        for _, _, body in ch.consume(queue=queue_name, auto_ack=True):
            data = json.loads(body)
            msg = f"{data['data']['reserva_id']} {status_text}"
            payments.appendleft(msg)
            if status_text == "Aprovado":
                log(f"✅ Reserva concluída: {msg}")
            else:
                log(f"❌ Pagamento recusado: {msg}")
    threading.Thread(target=run, args=("pagamento-aprovado", "Aprovado"), daemon=True).start()
    threading.Thread(target=run, args=("pagamento-recusado", "Recusado"), daemon=True).start()

def start_ticket_consumer():
    def run():
        conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
        ch = conn.channel()
        ch.queue_declare(queue="bilhete-gerado")
        for _, _, body in ch.consume(queue="bilhete-gerado", auto_ack=True):
            data = json.loads(body)
            msg = f"{data['bilhete_id']} → {data['destino']}"
            tickets.appendleft(msg)
            log(f"🎟️ Bilhete gerado: {msg}")
    threading.Thread(target=run, daemon=True).start()

def send_reservation(itinerary_id, passengers, cabins):
    try:
        conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
        ch = conn.channel()
        ch.queue_declare(queue="reserva-criada")
        payload = {
            "reserva_id": str(int(time.time() * 1000)),
            "itinerario_id": itinerary_id,
            "passageiros": passengers,
            "cabines": cabins
        }
        ch.basic_publish(exchange='', routing_key="reserva-criada", body=json.dumps(payload))
        log(f"📤 Reserva enviada: {payload['reserva_id']} ({itinerary_id})")
    except Exception as e:
        log(f"❗ Erro ao enviar reserva: {e}")

def render_dashboard():
    def build_table(title, col_name, data):
        table = Table(title=title, expand=True)
        table.add_column(col_name)
        for msg in list(data):
            table.add_row(msg)
        return table

    return Group(
        Panel(build_table("📢 Promoções", "Mensagem", promos)),
        Panel(build_table("💳 Pagamentos", "Status", payments)),
        Panel(build_table("🎟️ Bilhetes", "Bilhete → Destino", tickets)),
        Panel(build_table("📘 Logs", "Sistema", logs)),
        Panel("Digite: `reservar <ITINERARIO_ID> <PASSAGEIROS> <CABINES>`", title="✍️ Comandos"),
    )

def start_input_loop():
    session = PromptSession()
    while True:
        cmd = session.prompt("> ")
        if cmd.startswith("reservar"):
            try:
                _, itin, p, c = cmd.strip().split()
                send_reservation(itin, int(p), int(c))
            except Exception as e:
                log(f"❗ Comando inválido: {cmd}")
        else:
            log("ℹ️ Comando não reconhecido.")

def main():
    start_promotions_consumers()
    start_payment_consumers()
    start_ticket_consumer()

    threading.Thread(target=start_input_loop, daemon=True).start()

    with Live(render_dashboard(), refresh_per_second=1) as live:
        while True:
            time.sleep(1)
            live.update(render_dashboard())

if __name__ == "__main__":
    main()
