# MaxTrack 0.9.12 no ETS2

Atualize o aplicativo e feche o ETS2. Copie a `MaxTrackBridge.dll` da pasta `bridge` da nova instalação para `Euro Truck Simulator 2\bin\win_x64\plugins`, guardando uma cópia da DLL anterior. A nova DLL recebe a aproximação e suaviza o movimento entre os quadros do jogo.

Para ativar a aproximação, faça um backup do `controls.sii` do perfil do jogo. Na linha `mix trackirz`, substitua somente a expressão entre os acentos graves por `sdk.maxtrack.z?0`. A linha fica assim, com o índice que já existe no seu arquivo:

```text
config_lines[290]: "mix trackirz `sdk.maxtrack.z?0`"
```

Na cabine, sente na sua posição normal e aperte F10 olhando para a frente. Aproxime-se um pouco da webcam. O MaxTrack estima a aproximação pelo tamanho do rosto e envia um deslocamento limitado a 12 cm. Para desativar esse eixo, restaure a expressão anterior.

Para ver mais da cabine, aumente o campo de visão no menu F4 do próprio ETS2. [Menu de ajustes da SCS Software](https://blog.scssoft.com/2025/04/euro-truck-simulator-2-154-update.html)

Compare com o caminhão parado. Olhe devagar para os espelhos e depois volte ao centro. Se as viradas ainda parecerem travadas, anote o FPS de captura mostrado pelo MaxTrack e se a estimativa alterna entre PnP e geometria alinhada na aba Diagnóstico. O efeito visual da aproximação ainda precisa de validação na cabine.
