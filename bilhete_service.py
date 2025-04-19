import pika
import json
import uuid
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# carrega chave pública
with open("keys/pagamento_public.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read())

# carrega itinerários para mapear destino
with open('data/itinerarios.json') as f:
    itinerarios = json.load(f)

conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
ch = conn.channel()
ch.queue_declare(queue='pagamento-aprovado')
ch.queue_declare(queue='bilhete-gerado')

print("[MS Bilhete] Aguardando pagamentos aprovados...")

def callback(ch_, method, props, body):
    env = json.loads(body)
    data = env['data']
    sig = bytes.fromhex(env['signature'])

    # verifica assinatura
    public_key.verify(
        sig,
        json.dumps(data).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    res_id = data['reserva_id']
    itin = data.get('itinerario_id')
    destino = next((it['destino'] for it in itinerarios if it['id'] == itin), 'Desconhecido')
    bil_id = str(uuid.uuid4())

    payload = {'reserva_id': res_id, 'bilhete_id': bil_id, 'destino': destino}
    ch.basic_publish(exchange='', routing_key='bilhete-gerado', body=json.dumps(payload))
    print(f"[x] Bilhete gerado para {res_id}: {bil_id} ({destino})")

ch.basic_consume(queue='pagamento-aprovado', on_message_callback=callback, auto_ack=True)
ch.start_consuming()
