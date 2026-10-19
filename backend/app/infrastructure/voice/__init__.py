"""Motor de voz: quem falou, sem sair deste PC.

- `fbank`: feature log-mel compatível com Kaldi, em numpy.
- `embedder`: impressão vocal (WeSpeaker ResNet34 em ONNX).
- `vad`: detector de fala neural (Silero, já incluso no faster-whisper).
- `echo`: tira do microfone o eco do alto-falante.
- `tracker`: agrupa vozes na sessão e reconhece pessoas já cadastradas.
"""
