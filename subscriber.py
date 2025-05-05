import pika
import sys

def callback(ch, method, properties, body):
    destino = method.routing_key.replace('promocoes-', '')
    texto = body.decode()
    if destino == 'Minas Gerais':
        print("Minas não tem mar, bobo(a)!")
    print(f"[Promoção {destino}] {texto}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Uso: python {sys.argv[0]} destino1 [destino2 ...]")
        sys.exit(1)

    destinos = sys.argv[1:]
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    for d in destinos:
        queue = f"promocoes-{d}"
        channel.queue_declare(queue=queue)
        channel.basic_consume(queue=queue, on_message_callback=callback, auto_ack=True)

    print(f"Aguardando promoções para: {destinos}")
    channel.start_consuming()