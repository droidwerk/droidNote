<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="desktop/src/assets/logo-droidnote.png">
    <img alt="DroidNote" src="desktop/src/assets/logo-droidnote-on-light.png" width="440">
  </picture>
</p>

<p align="center">
  <strong>Assistente local de gravações.</strong><br>
  Transcreva e gere notas neste computador, sem conta obrigatória e sem bot no Meet, Teams ou Zoom.
</p>

<p align="center">
  <a href="https://github.com/droidwerk/droidNote/releases/latest/download/DroidNote-Setup.exe"><img src="https://img.shields.io/badge/Baixar_para_Windows-x64-FF4500?style=for-the-badge" alt="Baixar para Windows"></a>
  &nbsp;
  <a href="https://github.com/droidwerk/droidNote/releases/latest"><img src="https://img.shields.io/github/v/release/droidwerk/droidNote?style=for-the-badge&amp;label=vers%C3%A3o&amp;labelColor=333333&amp;color=FF4500" alt="Versão"></a>
</p>

<p align="center">
  Windows 10/11 · x64 · sem administrador<br>
  Português · English · Español · Italiano · Deutsch · Français · Русский
</p>

---

## O que faz

O DroidNote captura o microfone e, se você quiser, o áudio de outros aplicativos. A transcrição aparece ao vivo, já separada por voz: o motor de voz roda neste PC e mostra quem está falando agora. Dê nome a uma voz uma vez e o DroidNote a reconhece nas próximas gravações. No fim, gere uma nota para ditado, aula ou reunião.

| Captura | Quem falou | Transcrição | Notas |
| --- | --- | --- | --- |
| Microfone e áudio do sistema, neste PC | Separa as vozes pelo som, palavra a palavra | Whisper local ou API OpenAI | Resumo no dispositivo ou via OpenAI |
| Filtro de eco: sem fone, a chamada não entra duas vezes | Dê nome a uma voz uma vez; ela é reconhecida nas próximas gravações | Idioma da captura independente do idioma da interface | Chat sobre as sessões, com fontes. Ainda em beta |
| Sem bot convidado na chamada | Linha do tempo de quem falou quando e quanto | Busca em tudo o que já foi dito (`Ctrl+K`) | A ata atribui falas e ações a cada voz |

As ações da ata viram tarefas, com dono e prazo, reunidas numa lista só. A biblioteca guarda as sessões. Se você colar o endereço secreto do calendário (Google, Outlook ou iCloud), a próxima reunião aparece com o que ficou pendente.

A interface e a transcrição são duas escolhas distintas. O app pode ficar em português e a captura em alemão, por exemplo.

---

## Onde o áudio é processado

Você escolhe no primeiro uso e pode mudar em Preferências.

**Modelos locais.** Áudio, transcrição e notas permanecem neste computador. O app baixa o motor de transcrição (e, se faltar, o motor de notas) e mostra o tamanho antes de instalar.

**API OpenAI.** Mais preciso, com chave própria. O áudio da transcrição e trechos da nota saem deste PC e vão para a OpenAI. Vale a [política de privacidade da OpenAI](https://openai.com/policies/privacy-policy).

O arquivo WAV é opcional e pode ser desligado. A chave da API, se você usar uma, fica só nesta máquina.

Grave outras pessoas somente com o consentimento adequado. O app não avisa os demais participantes da chamada.

---

## Instalar

1. Baixe o [DroidNote-Setup.exe](https://github.com/droidwerk/droidNote/releases/latest/download/DroidNote-Setup.exe).
2. Execute o instalador **sem administrador**. Ele instala só para o usuário atual.
3. No primeiro uso, escolha o idioma da interface, o caminho de processamento e aceite os termos.

O Windows SmartScreen pode avisar na primeira execução enquanto o instalador não leva assinatura Authenticode. Use **Mais informações** e **Executar assim mesmo** se você baixou deste repositório.

Dados do usuário ficam em `%APPDATA%\DroidNote`. O programa fica em `%LOCALAPPDATA%\DroidNote`.

---

## Atualizar

Quem já está na 2.1.0 ou posterior vê um aviso quando sai uma versão nova. **Baixar** abre o instalador; **Agora não** esconde o aviso até a versão seguinte.

A instalação é por cima da atual. Notas, gravações e modelos não são apagados. A atualização não é automática.

---

## Documentação técnica

- [Arquitetura](docs/architecture.md): processos, camadas, dados, captura, notas, atualização
- [Desenvolvimento](docs/development.md): `dev.ps1`, testes, build do Setup
- [Diagnóstico e melhorias](docs/melhorias.md): o que foi medido, corrigido e o que vem a seguir

---

## Requisitos

- Windows 10 ou 11, 64 bits
- Microfone (e, para áudio do sistema, um dispositivo de loopback disponível)
- Espaço em disco para os modelos locais, se você escolher esse caminho

---

<p align="center">
  <a href="https://www.droidwerk.com.br/">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="desktop/src/assets/logo-droidwerk.png">
      <img alt="DroidWerk" src="desktop/src/assets/logo-droidwerk-on-light.png" width="200">
    </picture>
  </a><br>
  <sub>Produto <a href="https://www.droidwerk.com.br/">DroidWerk</a></sub>
</p>
