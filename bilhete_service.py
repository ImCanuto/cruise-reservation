import pika
import json
import uuid
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Carrega chave pública do MS Pagamento
with open("keys/pagamento_public.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read())

# Conexão
conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
chan = conn.channel()
chan.queue_declare(queue='pagamento-aprovado')
chan.queue_declare(queue='bilhete-gerado')

print("[MS Bilhete] Aguardando pagamentos aprovados...")

def callback(ch, method, props, body):
    env = json.loads(body)
    data = env['data']
    sig = bytes.fromhex(env['signature'])
    try:
        public_key.verify(
            sig,
            json.dumps(data).encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        res_id = data['reserva_id']
        bil_id = str(uuid.uuid4())
        chan.basic_publish(exchange='', routing_key='bilhete-gerado', body=json.dumps({'reserva_id': res_id, 'bilhete_id': bil_id}))
        print(f"[x] Bilhete gerado para {res_id}: {bil_id}")
    except Exception as e:
        print(f"Falha na verificação de assinatura: {e}")

chan.basic_consume(queue='pagamento-aprovado', on_message_callback=callback, auto_ack=True)
chan.start_consuming()