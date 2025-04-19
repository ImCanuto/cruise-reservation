import pika
import json
import uuid
import threading
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Carrega chave pública do MS Pagamento
with open("keys/pagamento_public.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read())

# Conexão RabbitMQ
def connect():
    conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    ch = conn.channel()
    # Declara filas
    for q in ['reserva-criada', 'pagamento-aprovado', 'pagamento-recusado', 'bilhete-gerado']:
        ch.queue_declare(queue=q)
    return conn, ch

conn, channel = connect()

# Callback para status de pagamento e bilhete
def on_message(ch, method, props, body):
    queue = method.routing_key
    if queue in ['pagamento-aprovado', 'pagamento-recusado']:
        envelope = json.loads(body)
        data = envelope['data']
        signature = bytes.fromhex(envelope['signature'])
        try:
            public_key.verify(
                signature,
                json.dumps(data).encode(),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
            if queue == 'pagamento-aprovado':
                print(f"[Reserva {data['reserva_id']}] Pagamento aprovado!")
            else:
                print(f"[Reserva {data['reserva_id']}] Pagamento recusado e reserva cancelada.")
        except Exception as e:
            print(f"Falha na verificação da assinatura: {e}")
    elif queue == 'bilhete-gerado':
        info = json.loads(body)
        print(f"[Reserva {info['reserva_id']}] Bilhete gerado: {info['bilhete_id']}")

# Inicia consumo em thread separada
def start_consuming():
    for q in ['pagamento-aprovado', 'pagamento-recusado', 'bilhete-gerado']:
        channel.basic_consume(queue=q, on_message_callback=on_message, auto_ack=True)
    channel.start_consuming()

t = threading.Thread(target=start_consuming, daemon=True)
t.start()

# Funções de interface CLI
def load_itinerarios():
    with open('data/itinerarios.json') as f:
        return json.load(f)

itinerarios = load_itinerarios()

while True:
    print("\n--- MS Reserva ---")
    print("1. Consultar itinerários")
    print("2. Efetuar reserva")
    print("0. Sair")
    opc = input("Escolha uma opção: ")

    if opc == '1':
        for it in itinerarios:
            print(f"ID: {it['id']} - {it['destino']} em {it['data_partida']} ({it['noites']} noites) - R${it['valor_por_pessoa']} por pessoa")
    elif opc == '2':
        res_id = str(uuid.uuid4())
        it_id = input("Informe o ID do itinerário: ")
        pax = input("Número de passageiros: ")
        cab = input("Número de cabines: ")
        msg = {
            'reserva_id': res_id,
            'itinerario_id': it_id,
            'passageiros': int(pax),
            'cabines': int(cab)
        }
        channel.basic_publish(exchange='', routing_key='reserva-criada', body=json.dumps(msg))
        print(f"Reserva criada (ID {res_id}), link de pagamento: http://pagamento.fake/pag?reserva_id={res_id}")
    elif opc == '0':
        conn.close()
        break
    else:
        print("Opção inválida.")