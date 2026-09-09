import { openExternal } from "../lib/openExternal";

const OPENAI_PRIVACY = "https://openai.com/policies/privacy-policy";
const OPENAI_KEYS = "https://platform.openai.com/api-keys";

interface PrivacyPolicyProps {
  compact?: boolean;
}

export function PrivacyPolicy({ compact = false }: PrivacyPolicyProps) {
  return (
    <div className={compact ? "privacy-body is-compact" : "privacy-body"}>
      <section>
        <h3>O que o DroidNote faz</h3>
        <p>
          O DroidNote captura áudio neste computador, transcreve e gera notas. Não há conta obrigatória
          nem bot convidado em Meet, Teams ou Zoom. A chave da API, se você usar uma, fica só nesta máquina.
        </p>
      </section>
      <section>
        <h3>Modo Modelos locais</h3>
        <p>
          Áudio, transcrição e notas permanecem neste computador. O arquivo WAV é
          opcional e pode ser desligado em Preferências.
        </p>
      </section>
      <section>
        <h3>Modo API OpenAI</h3>
        <p>
          Se você ligar a API OpenAI, o áudio da transcrição e trechos de texto usados em notas
          saem deste computador e vão para a OpenAI. O DroidNote não é o provedor do
          modelo. Vale a política de privacidade e os termos da OpenAI.
        </p>
        <p>
          <button type="button" className="text-link" onClick={() => void openExternal(OPENAI_KEYS)}>
            Como criar a chave
          </button>
          {" · "}
          <button type="button" className="text-link" onClick={() => void openExternal(OPENAI_PRIVACY)}>
            Privacidade da OpenAI
          </button>
        </p>
      </section>
      <section>
        <h3>Captura e terceiros</h3>
        <p>
          O app ouve o microfone e, se ligado, o áudio do sistema. Ele não avisa os outros participantes
          da chamada. Grave outras pessoas somente com o consentimento adequado.
        </p>
      </section>
    </div>
  );
}

export function PrivacyLink({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" className="text-link" onClick={onOpen}>
      Política de uso e privacidade
    </button>
  );
}
