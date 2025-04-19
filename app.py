from flask import Flask, render_template_string, request, jsonify, Response
from flask_cors import CORS
import pika, json, threading
from queue import Queue

app = Flask(__name__)
CORS(app)

# Filas internas para SSE
promo_queue = Queue()
backend_queue = Queue()
selected_destinations = []

# Inicia consumidores de backend (reserva, pagamento, bilhete)
def start_backend_consumers():
    def consume(queue_name):
        conn = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        ch = conn.channel()
        ch.queue_declare(queue=queue_name)
        for method, props, body in ch.consume(queue=queue_name, auto_ack=True):
            # formata mensagem e insere na fila
            backend_queue.put(f"[{queue_name}] {body.decode()}")
    for q in ['reserva-criada', 'pagamento-aprovado', 'pagamento-recusado', 'bilhete-gerado']:
        threading.Thread(target=consume, args=(q,), daemon=True).start()

start_backend_consumers()

# Consumidor de promoções por destino
def consume_promotions(dest):
    conn = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    ch = conn.channel()
    queue_name = f"promocoes-{dest}"
    ch.queue_declare(queue=queue_name)
    for method, props, body in ch.consume(queue=queue_name, auto_ack=True):
        promo_queue.put(f"[Promoção {dest}] {body.decode()}")

@app.route('/')
def index():
    html = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Reserva de Cruzeiros</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        section { border: 1px solid #ccc; padding: 10px; margin-bottom: 20px; }
        h2 { margin-top: 0; }
        #promo-notifs, #backend-logs { max-height: 200px; overflow-y: auto; background: #f9f9f9; padding: 5px; }
    </style>
</head>
<body>

<section>
    <h2>Registrar para Promoções</h2>
    <form id="promo-form">
        <label><input type="checkbox" name="destinations" value="Salvador"> Salvador</label>
        <label><input type="checkbox" name="destinations" value="Rio de Janeiro"> Rio de Janeiro</label>
        <label><input type="checkbox" name="destinations" value="Minas Gerais"> Minas Gerais</label>
        <button type="submit">Registrar</button>
    </form>
    <div id="promo-notifs"></div>
</section>

<section>
    <h2>Fazer Reserva</h2>
    <form id="reserve-form">
        <label>Itinerário:
            <select name="itinerary_id">
                <option value="ITN001">ITN001 - Salvador (2025-06-10)</option>
                <option value="ITN002">ITN002 - Rio de Janeiro (2025-07-20)</option>
            </select>
        </label>
        <label>Passageiros: <input type="number" name="passengers" value="1"></label>
        <label>Cabines: <input type="number" name="cabins" value="1"></label>
        <button type="submit">Reservar</button>
    </form>
    <div id="reserve-result"></div>
</section>

<section>
    <h2>Logs do Backend</h2>
    <div id="backend-logs"></div>
</section>

<script>
// Registrar inscrições
document.getElementById('promo-form').addEventListener('submit', e => {
    e.preventDefault();
    const checked = Array.from(document.querySelectorAll('input[name="destinations"]:checked')).map(cb => cb.value);
    fetch('/api/subscribe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({destinations: checked})
    });
});

// EventSource para promoções
const promoSource = new EventSource('/stream/promotions');
promoSource.onmessage = e => {
    const div = document.getElementById('promo-notifs');
    div.innerHTML += `<div>${e.data}</div>`;
    div.scrollTop = div.scrollHeight;
};

// EventSource para backend
const backendSource = new EventSource('/stream/backend');
backendSource.onmessage = e => {
    const div = document.getElementById('backend-logs');
    div.innerHTML += `<div>${e.data}</div>`;
    div.scrollTop = div.scrollHeight;
};

// Reserva via API
const resForm = document.getElementById('reserve-form');
resForm.addEventListener('submit', e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(resForm));
    fetch('/api/reserve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            reserva_id: Date.now().toString(),
            itinerario_id: data.itinerary_id,
            passageiros: parseInt(data.passengers),
            cabines: parseInt(data.cabins)
        })
    })
    .then(res => res.json())
    .then(json => {
        document.getElementById('reserve-result').innerText = json.message;
    });
});
</script>
</body>
</html>
'''    
    return render_template_string(html)

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    data = request.json or {}
    for dest in data.get('destinations', []):
        if dest not in selected_destinations:
            selected_destinations.append(dest)
            threading.Thread(target=consume_promotions, args=(dest,), daemon=True).start()
    return jsonify(success=True)

@app.route('/stream/promotions')
def stream_promotions():
    def event_stream():
        while True:
            msg = promo_queue.get()
            yield f"data: {msg}\n\n"
    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/stream/backend')
def stream_backend():
    def event_stream():
        while True:
            msg = backend_queue.get()
            yield f"data: {msg}\n\n"
    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/api/reserve', methods=['POST'])
def reserve():
    data = request.json
    conn = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    ch = conn.channel()
    ch.queue_declare(queue='reserva-criada')
    ch.basic_publish(exchange='', routing_key='reserva-criada', body=json.dumps(data))
    conn.close()
    return jsonify(success=True, message="Reserva concluída com sucesso")

if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0', port=5000)
