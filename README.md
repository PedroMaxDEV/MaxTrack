# MaxTrack 🎮

**Head tracking gratuito usando uma webcam comum para ETS2 e ATS.**

O MaxTrack detecta o movimento da cabeça com MediaPipe/OpenCV e envia Yaw/Pitch ao OpenTrack via UDP local (porta 4242). Não envia imagens para servidores.

> **Status: pré-lançamento.** Esta distribuição foi organizada a partir do código MaxTrack 0.9.3 recuperado. Ainda precisa de validação prática no Windows e no OpenTrack antes de anunciar uma versão estável.

## Instalação fácil (Windows 10/11)

1. Na aba **Actions** do GitHub, execute `Windows portable build` (ou baixe um artefato já gerado).
2. Extraia `MaxTrack-Windows-x64.zip` inteiro; abra `MaxTrack.exe` na pasta extraída. **Não precisa instalar Python.**
3. Instale o [OpenTrack](https://github.com/opentrack/opentrack/releases) separadamente.
4. No OpenTrack: **Input = UDP over network**, porta **4242**; **Output = freetrack 2.0 Enhanced**. Clique **Start**.
5. Abra o MaxTrack, selecione a webcam, ative com **F9**, centralize com **F10** e entre no ETS2/ATS.

Se não aparecer arquivo na aba Actions, execute o workflow manualmente ou crie uma tag `v0.9.3-rc1` para gerar uma Release.

## Recursos

- Webcam USB ou integrada, prévia local e detecção de rosto
- Sensibilidade horizontal/vertical, zona morta, suavização
- Inversão dos eixos e melhoria de imagem em pouca luz
- Atalhos F9 (pausar) e F10 (recentralizar)
- Configurações salvas em `%APPDATA%\MaxTrack\config.json`

## Desenvolvimento

Requer **Python 3.11 x64**. No Windows execute `scripts\run-dev.bat` ou:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src\maxtrack.py
```

Para compilar localmente execute `scripts\build.bat`.

## Documentação

- [Configurar OpenTrack e ETS2/ATS](docs/CONFIGURACAO.md)
- [Solução de problemas](docs/PROBLEMAS.md)
- [Contribuição](CONTRIBUTING.md)
- [English README](README_EN.md)

## Licença

MIT. Consulte [LICENSE](LICENSE). Dependências e OpenTrack têm licenças próprias.
