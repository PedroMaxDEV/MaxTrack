# Teste 0.9.10 — anti-tremor

A suavização temporal existente foi preservada. Um filtro de histerese na saída segura oscilações menores que a faixa configurada, em qualquer direção do olhar. Não é a mesma zona morta central: funciona também quando a cabeça está virada.

Novo controle: Anti-tremor, de 0 a 2 graus na saída. Valor inicial: 0,6. Zero reproduz a saída anterior, sem essa etapa. Não há atraso temporal adicional, mas há um pequeno deslocamento máximo igual à faixa durante movimentos lentos. Ajustes altos podem tornar movimentos pequenos menos perceptíveis.

Comece com 0,6, mantendo sua suavização atual. Compare cabeça parada olhando para frente e para os lados; depois faça movimentos lentos. Se necessário, experimente 1,0. Se perder precisão nos movimentos pequenos, reduza a faixa. F9/F10 e perda de tracking continuam enviando zero imediatamente.

Verificado automaticamente: oscilações de ±0,4 grau ficam estáveis com faixa 0,6; movimento lento acumulado continua avançando; deslocamento durante movimento limitado à faixa; desligar reproduz entrada; pausa/centro envia zero. 11 testes aprovados e smoke test de interface aprovado. Isso não comprova eliminação do tremor real, cuja amplitude ainda não foi medida.

Usuário relatou movimentos suaves mas tremor significativo na versão anterior. Verificação de causa e comparação visual no ETS2 continuam pendentes. ATS não instalado. Não classificar esta versão como pronta para lançamento comercial.
