# 0.9.11 — resposta e interface

Relato do usuário: tremor melhorou, mas as viradas parecem lentas. Configuração encontrada: suavização 0,61, anti-tremor 1,21 e pouca luz ligada. Não foi medida queda real de FPS nessa sessão.

Resposta adaptativa reduz a constante de tempo proporcionalmente à diferença entre o alvo e a posição filtrada, com limite mínimo de 25 ms. Nas pequenas variações a suavização permanece mais forte. A opção “Resposta rápida nas viradas” desligada reproduz exatamente a equação anterior. Detecção, calibração, sensibilidade e limites permanecem iguais. O anti-tremor continua separado.

Botão “Aplicar ajuste de resposta rápida”: suavização 0,25, anti-tremor 0,6, resposta adaptativa ligada e pouca luz desligada. Não altera inversões, sensibilidade, câmera ou saída. Não é aplicado automaticamente sobre as preferências salvas.

Interface: prévia e ações fixas à esquerda; perfil e abas Movimento, Câmera e saída, Diagnóstico à direita. FPS de captura/processamento visível no cabeçalho (não é o FPS do ETS2). Diagnósticos técnicos retirados da área principal.

14 testes automatizados aprovados, incluindo equivalência da equação antiga quando a resposta adaptativa está desativada e teste que limita a mudança no loop de tracking ao cálculo de alpha. Smoke test de Tk/perfis aprovado. Redução real da lentidão e estabilidade no jogo precisam de comparação manual. Não há alegação de aumento de FPS.
