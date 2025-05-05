import pika
import json
import random
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# carrega a chave privada que será usada para assinar os dados das reservas
with open("keys/pagamento_private.pem", "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

# conecta ao servidor RabbitMQ
conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
# cria um canal de comunicação com o RabbitMQ para enviar e receber mensagens
ch = conn.channel()

# declara um exchange 'pagamento' direct para direcionar mensagens
ch.exchange_declare(exchange='pagamento', exchange_type='direct')
# declara a fila que irá receber as reservas criadas
ch.queue_declare(queue='reserva-criada')

# mensagem de inicialização do terminal
print("[MS Pagamento] Aguardando reservas...")

# função que processa cada nova reserva recebida da fila
def callback(ch_, method, props, body):
    msg = json.loads(body)
# xxtrai o ID da reserva da mensagem recebida
    res_id = msg['reserva_id']
# randomiza o pagamento (aprovado ou recusado)
    approved = random.choice([True, False])
# prepara os dados que serão enviados
    data = {
        'reserva_id': res_id,
        'itinerario_id': msg.get('itinerario_id')
    }
# assina digitalmente os dados
    sig = private_key.sign(
    json.dumps(data, sort_keys=True).encode(),
    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
    hashes.SHA256()
    )
# junta tudo em um envelope
    envelope = {'data': data, 'signature': sig.hex()}

# define o nome da routing_jey com base na aprovação ou recusa do pagamento
    rk = 'pagamento-aprovado' if approved else 'pagamento-recusado'
# envia a mensagem para o exchange com a rota apropriada
    ch.basic_publish(
        exchange='pagamento',
        routing_key=rk,
        body=json.dumps(envelope)
    )
# exibe no terminal o status da reserva
    print(f"[x] Pagamento {'APROVADO' if approved else 'RECUSADO'} para {res_id}")

# configura o consumidor para escutar a fila de reservas criadas
ch.basic_consume(queue='reserva-criada', on_message_callback=callback, auto_ack=True)
# inicia o consumo das mensagens da fila
ch.start_consuming()
