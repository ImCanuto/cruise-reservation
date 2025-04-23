import pika
import json
import random
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# carrega chave privada
with open("keys/pagamento_private.pem", "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
ch = conn.channel()

# exchange DIRECT para streaming de pagamentos
ch.exchange_declare(exchange='pagamento', exchange_type='direct')
ch.queue_declare(queue='reserva-criada')

print("[MS Pagamento] Aguardando reservas...")

def callback(ch_, method, props, body):
    msg = json.loads(body)
    res_id = msg['reserva_id']
    # randomiza o pagamento (aprovado ou recusado)
    approved = random.choice([True, False])
    data = {
        'reserva_id': res_id,
        'itinerario_id': msg.get('itinerario_id')
    }
    sig = private_key.sign(
        json.dumps(data).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    envelope = {'data': data, 'signature': sig.hex()}

    # publica no exchange 'pagamento' com routing_key apropriada
    rk = 'pagamento-aprovado' if approved else 'pagamento-recusado'
    ch.basic_publish(
        exchange='pagamento',
        routing_key=rk,
        body=json.dumps(envelope)
    )
    print(f"[x] Pagamento {'APROVADO' if approved else 'RECUSADO'} para {res_id}")

ch.basic_consume(queue='reserva-criada', on_message_callback=callback, auto_ack=True)
ch.start_consuming()
