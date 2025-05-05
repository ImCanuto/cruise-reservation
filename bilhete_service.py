import pika
import json
import uuid
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# abre e carrega a chave pública do serviço de pagamento para verificação das assinaturas
with open("keys/pagamento_public.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read())

# mapeia destinos
with open('data/itinerarios.json') as f:
    itinerarios = json.load(f)

# estabelece conexão com o servidor RabbitMQ
conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
# cria um canal de comunicação com o RabbitMQ
ch = conn.channel()

# declara um exchange do direct para receber mensagens de pagamento
ch.exchange_declare(exchange='pagamento', exchange_type='direct')
# cria uma fila exclusiva para este consumidor
queue_name = ch.queue_declare(queue='', exclusive=True).method.queue
# liga a fila ao exchange, mas só para mensagens de pagamento aprovado
ch.queue_bind(exchange='pagamento', queue=queue_name, routing_key='pagamento-aprovado')

# mensagem de inicialização do terminal
print("[MS Bilhete] Aguardando pagamentos aprovados...")

# callback sempre que uma nova mensagem de pagamento aprovado for recebida
def callback(ch_, method, props, body):
# carrega o conteúdo da mensagem recebida
    env = json.loads(body)
    data = env['data']
# converte a assinatura recebida de hexadecimal para bytes
    sig = bytes.fromhex(env['signature'])

# verifica se a assinatura é válida
    public_key.verify(
        sig,
        json.dumps(data, sort_keys=True).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
# extrai o ID da reserva da mensagem
    res_id = data['reserva_id']
    itin_id = data.get('itinerario_id')
# encontra o destino correspondente ao itinerário recebido na mensagem
    destino = next((it['destino'] for it in itinerarios if it['id'] == itin_id), 'Desconhecido')
# gera um ID único para o novo bilhete
    bil_id = str(uuid.uuid4())
# cria o conteúdo do bilhete a ser enviado para outra fila
    payload = {'reserva_id': res_id, 'bilhete_id': bil_id, 'destino': destino}
# envia o bilhete gerado para a fila
    ch.basic_publish(exchange='', routing_key='bilhete-gerado', body=json.dumps(payload))
# exibe no terminal que o bilhete foi gerado
    print(f"[x] Bilhete gerado para {res_id}: {bil_id} ({destino})")

# registra a função de callback para a fila
ch.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
# começa a escutar a fila por novas mensagens
ch.start_consuming()
