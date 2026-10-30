<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="desktop/src/assets/logo-droidnote.png">
    <img alt="DroidNote" src="desktop/src/assets/logo-droidnote-on-light.png" width="420">
  </picture>
</p>

<p align="center">
  <strong>O notetaker de reuniões e aulas que roda no seu PC.</strong><br>
  Transcrição ao vivo com identificação de voz, ata com evidências, tarefas, mapa mental e memória entre reuniões — tudo neste computador, sem bot na chamada.
</p>

<p align="center">
  <a href="https://github.com/droidwerk/droidNote/releases/latest/download/DroidNote-Setup.exe"><img src="https://img.shields.io/badge/Baixar_para_Windows-x64-FF4400?style=for-the-badge" alt="Baixar para Windows"></a>
  &nbsp;
  <a href="https://github.com/droidwerk/droidNote/releases/latest"><img src="https://img.shields.io/github/v/release/droidwerk/droidNote?style=for-the-badge&label=vers%C3%A3o&labelColor=333333&color=FF4400" alt="Versão"></a>
</p>

<p align="center">
  <a href="https://github.com/droidwerk/droidNote/actions/workflows/release.yml"><img src="https://img.shields.io/github/actions/workflow/status/droidwerk/droidNote/release.yml?branch=main&label=build&labelColor=333333" alt="Build"></a>
  <a href="https://github.com/droidwerk/droidNote/releases"><img src="https://img.shields.io/github/downloads/droidwerk/droidNote/total?labelColor=333333&color=FF4400" alt="Downloads"></a>
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/changelog-keep_a_changelog-333333" alt="Changelog"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-333333" alt="License: AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/plataforma-Windows_10%2F11-333333" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/idiomas-7-333333" alt="7 idiomas">
</p>

<p align="center">
  <a href="README.md">🇺🇸 English</a> · <a href="docs/architecture.md">Arquitetura</a> · <a href="docs/development.md">Desenvolvimento</a> · <a href="docs/ROADMAP.md">Roadmap</a> · <a href="CHANGELOG.md">Changelog</a>
</p>

---

O DroidNote grava o microfone e, se você quiser, o áudio de outros aplicativos (Meet, Teams, Zoom, um vídeo, uma aula) e transforma isso em transcrição, ata, tarefas e mapa mental. Ele não entra na chamada como bot e não exige conta. Tudo pode rodar no seu próprio computador; a API da OpenAI é uma escolha opcional para quem quer mais precisão.

A interface está em português, inglês, espanhol, italiano, alemão, francês e russo, e o idioma da transcrição é independente do idioma da interface.

<p align="center">
  <img src="docs/screenshots/session.png" alt="Uma reunião no DroidNote: transcrição com falantes, ata com marcas de tempo e as abas laterais" width="900">
</p>

## O que você pode fazer

| | |
| --- | --- |
| 🎙️ **Captura** | Microfone e áudio do sistema, neste PC. Filtro de eco: uma chamada sem fone não entra duas vezes. Sem bot convidado na reunião. |
| 🗣️ **Quem falou** | As vozes são separadas pelo som, em tempo real. Dê nome a uma voz uma vez e o DroidNote a reconhece nas próximas gravações — o aviso "falando agora" mostra o nome antes mesmo de a transcrição chegar. |
| 📝 **Transcrição** | Whisper local (GPU ou CPU) ou API OpenAI. Cada linha tem o seu momento; busque em tudo o que já foi dito com `Ctrl+K`. |
| 📄 **Ata** | Assuntos, decisões, ações e pendências, cada item terminando com o momento da transcrição que o sustenta. Clique na marca de tempo para ouvir. Templates por tipo de reunião. |
| ✅ **Tarefas** | As ações da ata viram tarefas com dono e prazo, numa lista só, de todas as reuniões. |
| 🧠 **Mapa mental** | Montado a partir da ata, sem custo: assuntos, decisões, ações, pendências e material, cada folha ligada à fala. Editável; "Reorganizar com IA" reagrupa os ramos sem perder nenhuma folha. |
| 🔁 **Memória entre reuniões** | Reuniões com o mesmo título ou as mesmas pessoas formam uma série. Antes da reunião: o que foi decidido e o que ficou aberto. Depois: o que foi resolvido, o que mudou, o que é novo. |
| 📎 **Contexto** | Suba a pauta, os slides ou um contrato para a reunião. A ata e o chat passam a usar os nomes e termos certos. |
| 💬 **Chat** | Pergunte sobre uma reunião ou sobre todas, com fontes que abrem no ponto certo. Anexe documentos (PDF, Word, Excel). |
| 🗓️ **Briefing do calendário** | Cole o endereço ICS secreto do seu calendário (Google, Outlook, iCloud) e a próxima reunião aparece com o que ficou pendente. |
| 📤 **Exportar** | Markdown, PDF e Word com a cara do DroidNote; o mapa mental em PNG. |

<p align="center">
  <img src="docs/screenshots/mindmap.png" alt="A aba Mapa: assuntos, decisões e ações da reunião em ramos, cada folha ligada à transcrição" width="900">
</p>

## Onde o áudio é processado

Você escolhe no primeiro uso e pode mudar em Preferências.

| | Modelos locais | API OpenAI |
| --- | --- | --- |
| Áudio e texto | Ficam neste computador | Janelas de áudio e o texto da ata vão para a OpenAI |
| Transcrição | Whisper `large-v3-turbo` em placa NVIDIA (6 GB+), `small` na CPU | `gpt-transcribe` |
| Ata, chat, mapa | Gemma 4 ou Qwen 3.6 pelo [Ollama](https://ollama.com), no tamanho que a sua RAM e placa de vídeo aguentam | `gpt-6-luna` (padrão), `gpt-5.6-luna`, `gpt-5.6-terra` |
| Custo | Grátis; um download de alguns GB, uma vez | Sua chave, paga por uso — uma reunião de 1 hora custa centavos |
| Precisão | Boa; nomes próprios e fala cruzada são mais difíceis | A melhor |

O assistente de instalação lê a RAM, a placa de vídeo e o disco livre e explica quais modelos escolheu e por quê. Guardar o WAV é opcional. A chave da API, se você usar uma, fica só nesta máquina.

Grave outras pessoas somente com o consentimento adequado. O DroidNote não avisa os demais participantes da chamada; um aviso pronto para colar está a um clique na tela ao vivo.

## Começar

1. Baixe o [DroidNote-Setup.exe](https://github.com/droidwerk/droidNote/releases/latest/download/DroidNote-Setup.exe).
2. Execute o instalador **sem administrador**; ele instala só para o usuário atual.
3. No primeiro uso, escolha o idioma da interface, modelos locais ou API OpenAI, e aceite os termos. O assistente mostra o que será baixado e o tamanho.
4. Abra **Ao vivo**, escolha *Ditado*, *Aula* ou *Reunião* e grave.

O Windows SmartScreen pode avisar na primeira execução enquanto o instalador não tem assinatura Authenticode. Use **Mais informações → Executar assim mesmo** se você baixou deste repositório.

**Atualizar.** Instale a versão nova por cima da atual; notas, gravações e modelos são mantidos. O app avisa quando sai uma versão nova; a atualização nunca é automática.

**Onde ficam as coisas.** Dados do usuário em `%APPDATA%\DroidNote`, o programa em `%LOCALAPPDATA%\DroidNote`, modelos Whisper na pasta de dados, modelos Ollama na pasta do próprio Ollama.

### Ou deixe seu agente de IA instalar

Cole a linha do agente que você usa; ele roda o script oficial, confere o checksum do instalador e abre o app. Detalhes e o que o script faz: [Instalar com seu agente de IA](docs/INSTALL_WITH_AI.md). O prompt pode ser em português.

| Agente | Comando |
| --- | --- |
| Claude Code | `claude "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| Codex CLI | `codex "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| Gemini CLI | `gemini -i "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| Copilot CLI | `copilot -p "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| Cursor CLI | `cursor-agent "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| Sem agente | `irm https://github.com/droidwerk/droidNote/releases/latest/download/install.ps1 \| iex` |

## Plataformas

| Plataforma | Situação |
| --- | --- |
| Windows 10/11 x64 | ✅ Instalador em toda release |
| macOS | 🗺️ No [roadmap](docs/ROADMAP.md) — a captura de áudio hoje é só Windows |
| Linux | 🗺️ No roadmap |

Requisitos: Windows 64 bits, microfone (e, para o áudio do sistema, um dispositivo de loopback), espaço em disco para os modelos locais se você escolher esse caminho. Uma placa NVIDIA com 6 GB ou mais deixa a transcrição local bem mais rápida, mas não é obrigatória.

## Como é feito

Um app desktop [Tauri 2](https://tauri.app) com interface React + TypeScript e um sidecar Python (FastAPI) que faz o trabalho pesado: captura de áudio com WASAPI, [faster-whisper](https://github.com/SYSTRAN/faster-whisper) na transcrição, um embedder de voz [WeSpeaker](https://github.com/wenet-e2e/wespeaker) em ONNX para identificar quem fala, Ollama ou API OpenAI para os modelos de linguagem e SQLite para guardar tudo. O editor do mapa mental é o [mind-elixir](https://github.com/SSShooter/mind-elixir-core).

- [Arquitetura](docs/architecture.md) — processos, camadas, dados, captura e motor de voz
- [Desenvolvimento](docs/development.md) — rodar em dev, testes, build do instalador
- [Releases](docs/RELEASING.md) — versionamento, o workflow de release e o changelog
- [Roadmap](docs/ROADMAP.md) — o que vem a seguir

## Versionamento

O DroidNote segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/): `MAJOR.MINOR.PATCH`. Todo push na `main` que passa nos testes publica uma release patch; `[release minor]` ou `[release major]` na mensagem do commit sobe as outras partes. Cada release é uma tag Git (`v2.2.5`), uma release no GitHub com os instaladores e uma seção datada no [changelog](CHANGELOG.md).

## Contribuir, suporte e segurança

- Bugs e ideias: [abra uma issue](https://github.com/droidwerk/droidNote/issues) usando os modelos.
- Código: escrito pela DroidWerk e por colaboradores convidados. Pull requests não solicitados são fechados; descreva sua correção numa issue. Veja o [CONTRIBUTING.md](.github/CONTRIBUTING.md).
- Ajuda com instalação ou modelos: [SUPPORT.md](.github/SUPPORT.md).
- Vulnerabilidades: **nunca em issue pública** — veja [SECURITY.md](.github/SECURITY.md).

## Licença

O DroidNote é software livre sob a [GNU Affero General Public License v3.0](LICENSE). Você pode usar, estudar, modificar e compartilhar; se distribuir uma versão modificada ou oferecê-la por rede, precisa disponibilizar o código sob os mesmos termos.

```
DroidNote — transcrição, ata e memória de reuniões, no seu próprio PC.
Copyright (C) 2026 DroidWerk

Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob os
termos da GNU Affero General Public License publicada pela Free Software
Foundation, na versão 3 da licença ou (a seu critério) qualquer versão posterior.

Este programa é distribuído na esperança de que seja útil, mas SEM QUALQUER
GARANTIA; sem sequer a garantia implícita de COMERCIALIZAÇÃO ou ADEQUAÇÃO A UM
FIM ESPECÍFICO. Veja a GNU Affero General Public License para mais detalhes.
```

- Os **nomes e logos DroidNote e DroidWerk são marcas** e não estão cobertos pela AGPL: veja [TRADEMARK.md](TRADEMARK.md).
- Componentes e modelos de terceiros mantêm as licenças deles, listadas em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Os modelos são baixados das fontes oficiais; o assistente mostra o que será baixado antes de instalar.

---

<p align="center">
  <a href="https://www.droidwerk.com.br/">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="desktop/src/assets/logo-droidwerk.png">
      <img alt="DroidWerk" src="desktop/src/assets/logo-droidwerk-on-light.png" width="180">
    </picture>
  </a><br>
  <sub>Produto <a href="https://www.droidwerk.com.br/">DroidWerk</a></sub>
</p>
