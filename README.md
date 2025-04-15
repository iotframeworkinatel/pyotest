# pyotest


# pyotest

## 1 - Requisitos do Pyotest

Para que o Pyotest seja eficiente, ele deve atender aos seguintes requisitos:

### Funcionais

* Testes de segurança IoT: Deve ser capaz de testar vulnerabilidades comuns como autenticação fraca, APIs inseguras, portas abertas e falta de criptografia.
* Suporte a múltiplos protocolos: MQTT, CoAP, HTTP, Telnet, SSH, etc.
* Automação de testes: Integração com pipelines de CI/CD (GitHub Actions, Jenkins).
* Execução em contêineres: Testes isolados em ambientes Docker.
* Testes de firmware: Análise de firmwares extraídos dos dispositivos.
* Simulação de tráfego malicioso: Permitir ataques de força bruta, sniffing de tráfego, etc.
* Relatórios detalhados: Mapear vulnerabilidades encontradas com as diretrizes do OWASP IoT Top 10.

### Não Funcionais

* Modularidade: Arquitetura baseada em plugins para extensibilidade.
* Facilidade de uso: Deve ser simples para desenvolvedores integrarem novos casos de teste.
* Escalabilidade: Suporte a execução de testes em vários dispositivos simultaneamente.
* Código aberto: Deve estar disponível no GitHub para colaboração.


## Bibliotecas Essenciais

- **pytest**: Estrutura de testes.
- **scapy**: Manipulação de pacotes de rede.
- **python-nmap**: Scanner de portas.
- **requests**: Testes de APIs inseguras.
- **Binwalk**: Análise de firmware.


