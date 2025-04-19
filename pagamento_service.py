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
for q in ['reserva-criada', 'pagamento-aprovado', 'pagamento-recusado']:
    ch.queue_declare(queue=q)

print("[MS Pagamento] Aguardando reservas...")

def callback(ch_, method, props, body):
    msg = json.loads(body)
    res_id = msg['reserva_id']
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
    env = {'data': data, 'signature': sig.hex()}

    if approved:
        ch.basic_publish(exchange='', routing_key='pagamento-aprovado', body=json.dumps(env))
        print(f"[x] Pagamento aprovado para {res_id}")
    else:
        ch.basic_publish(exchange='', routing_key='pagamento-recusado', body=json.dumps(env))
        print(f"[x] Pagamento recusado para {res_id}")

ch.basic_consume(queue='reserva-criada', on_message_callback=callback, auto_ack=True)
ch.start_consuming()
