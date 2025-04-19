import pika
import json
import random
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Carrega private key do MS Pagamento
with open("keys/pagamento_private.pem", "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

# Conexão
conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
chan = conn.channel()
# Declara filas
for q in ['reserva-criada', 'pagamento-aprovado', 'pagamento-recusado']:
    chan.queue_declare(queue=q)

print("[MS Pagamento] Aguardando reservas...")

def callback(ch, method, props, body):
    msg = json.loads(body)
    res_id = msg['reserva_id']
    approved = random.choice([True, False])
    data = {'reserva_id': res_id}
    sig = private_key.sign(
        json.dumps(data).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    envelope = {'data': data, 'signature': sig.hex()}

    if approved:
        chan.basic_publish(exchange='', routing_key='pagamento-aprovado', body=json.dumps(envelope))
        print(f"[x] Pagamento aprovado para {res_id}")
    else:
        chan.basic_publish(exchange='', routing_key='pagamento-recusado', body=json.dumps(envelope))
        print(f"[x] Pagamento recusado para {res_id}")

chan.basic_consume(queue='reserva-criada', on_message_callback=callback, auto_ack=True)
chan.start_consuming()