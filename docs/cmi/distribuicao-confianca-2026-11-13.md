# Distribuição, SmartScreen e confiança — 2026-11-13

Pesquisa: cmi-pesquisador. Fontes primárias Microsoft de out/2026.

## Estado do repo
- Sem assinatura de código: `desktop/src-tauri/tauri.conf.json` só tem `digestAlgorithm` e `timestampUrl`; `release.yml` sem passo de assinatura nem attestation. A reputação SmartScreen recomeça a cada versão (reputação é por hash quando não há certificado).
- Chave de API: `backend/app/core/secrets.py` cifra com DPAPI (escopo do usuário, prefixo `dpapi:v1:`). Prática correta no Windows. Fora do Windows fica só em base64. Melhoria barata: `pOptionalEntropy`.

## Q1. Acabar com o SmartScreen
1. **Certificado OV em nome da DroidWerk (CNPJ)** — US$ 150–300/ano (Certum Standard Cloud a partir de €209). Chave em HSM/nuvem. Não remove o aviso na hora: reputação acumula com a mesma identidade. Tauri via `signCommand`.
2. **SignPath Foundation** — grátis para OSS; editor exibido é "SignPath Foundation". Exige licença OSI, MFA, aprovação manual por release. Pode recusar.
3. **Certum Open Source** — €49/ano; pessoa física ("Open Source Developer" + nome do CEO).
4. **Azure Artifact Signing** — US$ 9,99/mês, mas só EUA/CA/UE/UK. **Brasil fora.**
5. **EV** — não vale: desde 2024 se comporta igual ao OV no SmartScreen.

Extra: nunca substituir asset publicado; enviar falsos positivos ao Microsoft Defender (File Submission).

## Q2. Distribuição alternativa
1. **Microsoft Store, listagem EXE/MSI** — cadastro gratuito (pessoa física desde set/2025; empresa: a confirmar). Instalação pela Store não mostra SmartScreen. Exige instalador assinado (depende da Q1). Tauri tem guia oficial (`webviewInstallMode: offlineInstaller`, `/S` no NSIS).
2. **Store MSIX** — único caminho sem aviso e sem custo (Microsoft reassina). Tauri não gera MSIX; esforço alto (backend Python, microfone, updates via Store).
3. **winget** — grátis, PR no microsoft/winget-pkgs. Não resolve o aviso do download pelo navegador.
4. **Chocolatey / Scoop** — público técnico pequeno.

## Q3. Plugin / marketplace
- Diretório da Anthropic não aceita mais MCPB/.dxt desde 25/09/2026 (só plugin bundle ou conector remoto).
- Viável só como **complemento**: MCP local que lê as reuniões do DroidNote. MCP empacotado no Windows também exige assinatura.

## Q4. Selos de confiança
1. **GitHub Artifact Attestations (SLSA L2 / Sigstore)** — grátis; `actions/attest`; usuário verifica com `gh attestation verify`.
2. **OpenSSF Scorecard e Best Practices Badge** — grátis.
3. **Link do VirusTotal por release** — grátis, evidência fraca.
4. **Política de privacidade + SECURITY.md + explicação do DPAPI na tela de configurações.**
5. **SOC 2 / ISO 27001** — caros e voltados a nuvem; não se justificam para app local.

## Recomendação
1. OV em nome da DroidWerk (ou tentar SignPath antes).
2. Com instalador assinado, publicar na Store como EXE.
3. Attestations no release.yml.
4. winget.
5. MCP de leitura das reuniões como complemento.

## Fontes
- https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/distribution-feature-status
- https://v2.tauri.app/distribute/microsoft-store/
- https://shop.certum.eu/open-source-code-signing-on-simplysign.html
- https://signpath.org/terms.html
- https://claude.com/docs/directory/publish
- https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds
- https://blogs.windows.com/windowsdeveloper/2025/09/10/free-developer-registration-for-individual-developers-on-microsoft-store/
- https://github.com/microsoft/winget-pkgs/blob/master/DevOpsPipelineDefinitions/validation-pipeline.yaml

## Atualização: custo zero e sem .exe (decisão do CEO, 2026-11-13)

O CEO não quer comprar nada nem distribuir .exe. As recomendações de OV/EV/Azure acima ficam descartadas.

| # | Opção | Custo | Tira aviso | UX leigo | Esforço |
|---|---|---|---|---|---|
| 1 | Microsoft Store MSIX (WinApp CLI, `winapp pack`) | 0 | Sim, inclui Smart App Control (a Microsoft reassina) | Ótima | Médio-alto |
| 2 | SignPath Foundation + winget/script | 0 | Sim, depois de aprovado | Boa | Médio, sujeito a aprovação |
| 3 | winget sem assinatura | 0 | Parcial (Smart App Control bloqueia) | Média | Baixo |
| 4 | install.ps1 / Scoop | 0 | Parcial (Smart App Control bloqueia) | Média-ruim | Já existe |
| 5 | PyPI + uvx, UI no navegador | 0 | Parcial | Ruim | Médio |

- Cadastro de empresa na Store grátis desde 07/05/2026 (storedeveloper.microsoft.com, D-U-N-S ou documento). Brasil para conta de empresa: não confirmado.
- MSIX full trust exige `rescap:runFullTrust` justificado. Pasta do pacote é só leitura: cache do Python em %LOCALAPPDATA%. Atualização passa a ser pela Store (desligar o updater do Tauri na build da Store).
- A permissão de microfone do python.exe filho dentro do MSIX não foi testada.

Fontes: https://www.neowin.net/news/microsoft-makes-company-developer-accounts-free-for-the-microsoft-store/ · https://learn.microsoft.com/en-us/windows/apps/dev-tools/winapp-cli/ · https://github.com/microsoft/winappCli/blob/main/samples/tauri-app/README.md · https://github.com/microsoft/winget-cli/issues/797 · https://signpath.org/apply.html
