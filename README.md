# Sistema Distribuído de Reservas de Cruzeiro 🛳️

Este projeto foi desenvolvido para a disciplina de **Sistemas Distribuídos** e consiste em um conjunto de microserviços que simulam um fluxo de reservas de cruzeiro, incluindo:

- **MS Marketing**: publica promoções para destinos.
- **MS Reserva**: recebe pedidos de reserva e gera identificador.
- **MS Pagamento**: processa pagamentos (aprovados ou recusados) e publica status.
- **MS Bilhete**: gera bilhetes após pagamento aprovado.
- **Dashboard Interativo**: exibe em tempo real promoções, status de pagamento, geração de bilhetes e logs, usando **Textual**.

Cada serviço comunica-se via **RabbitMQ**, adotando padrão **pub/sub** para garantir que múltiplos consumidores recebam todas as mensagens.

---

## 📁 Estrutura do Projeto

```text
project-root/
│
├── app_dashboard.py          # Cliente Textual (dashboard)
├── marketing_service.py      # Publicador de promoções
├── pagamento_service.py      # Serviço de validação de pagamentos (pub/sub)
├── bilhete_service.py        # Serviço de geração de bilhetes
├── generate_keys.py          # Gera as chaves RSA
├── data/                     # Dados de itinerários (JSON)
│   └── itinerarios.json
├── keys/                     # Chaves RSA para assinatura/verificação
│   ├── pagamento_private.pem
│   └── pagamento_public.pem
└── README.md
```

---

## 🚀 Dependências

- **Python 3.8+**
- **RabbitMQ** (broker AMQP)
- Bibliotecas Python (instalar via `pip`):
  ```bash
  pip install pika textual rich cryptography
  ```

---

## 🔧 Configuração Inicial

1. **Instalar RabbitMQ** e deixá‑lo rodando em `localhost:5672`.
2. **Gerar chaves RSA**: execute o script `generate_keys.py` para gerar automaticamente as chaves pública e privada:
   ```bash
   python generate_keys.py
   ```
3. **Dados de itinerários**: verifique `data/itinerarios.json`. Adicione ou edite destinos, datas, preços.

---

## 📚 Como Executar

Abra **seis** terminais (ou abas/tmux):

1. **MS Marketing** (envia promoções contínuas):
   ```bash
   python marketing_service.py Salvador "Rio de Janeiro" Minas Gerais
   ```

2. **MS Reserva** (CLI de reservas):
   ```bash
   python reserva_service.py
   ```
   - Menu interativo para consultar itinerários e criar reservas.

3. **MS Pagamento** (pub/sub):
   ```bash
   python pagamento_service.py
   ```
   - Escuta `reserva-criada` e publica em exchange `pagamento`:
     - `pagamento-aprovado` ou `pagamento-recusado`.

4. **MS Bilhete** (pub/sub):
   ```bash
   python bilhete_service.py
   ```
   - Consome apenas `pagamento-aprovado`, gera e publica bilhetes em fila `bilhete-gerado`.

5. **Dashboard Interativo**:
   ```bash
   python app_dashboard.py
   ```
   - Exibe em tempo real:
     - 📢 *Promoções* (fila `promocoes-<destino>`)
     - 💳 *Pagamentos* (exchange `pagamento`)
     - 🎟️ *Bilhetes* (`bilhete-gerado`)
     - 📘 *Logs* de eventos e erros
   - Comando interno: `reservar <ITINERARIO_ID> <PASSAGEIROS> <CABINES>`
   - Pressione `q` para sair.

---

## ✅ Fluxo de uma Reserva

1. Usuário digita `reservar ITN001 2 1` no **dashboard** ou no **MS Reserva**.
2. Mensagem `reserva-criada` publicada na fila padrão.
3. **MS Pagamento** consome e publica **pub/sub** em `pagamento-aprovado` ou `pagamento-recusado`.
4. **Dashboard** e **MS Bilhete** recebem o status (todos as mensagens).
5. Se **aprovado**, **MS Bilhete** gera e publica bilhete na fila `bilhete-gerado`.
6. **Dashboard** mostra pagamento e, em seguida, bilhete gerado.

---

## 📄 Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

---

### Desenvolvido para Sistemas Distribuídos - UTFPR
**Samuel Canuto Sales de Oliveira** | 2025
<br>
**Giulia Cavasin** | 2025