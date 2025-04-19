import pika
import sys
import time

# Destinos válidos: Salvador, Rio de Janeiro, Minas Gerais
destinos = ['Salvador', 'Rio de Janeiro', 'Minas Gerais']

def main():
    if len(sys.argv) < 2:
        print(f"Uso: python {sys.argv[0]} destino1 [destino2 ...]")
        sys.exit(1)

    selected = sys.argv[1:]
    for d in selected:
        if d not in destinos:
            print(f"Destino inválido: {d}")
            sys.exit(1)

    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    # Declara filas para cada destino
    for d in selected:
        channel.queue_declare(queue=f"promocoes-{d}")

    print(f"Publicando promoções para: {selected}")
    try:
        while True:
            for d in selected:
                message = f"Promoção imperdível para {d}!"
                channel.basic_publish(exchange='', routing_key=f"promocoes-{d}", body=message)
                print(f"[x] Promoção enviada para {d}")
                time.sleep(5)
    except KeyboardInterrupt:
        connection.close()
        print("Marketing service encerrado.")

if __name__ == '__main__':
    main()