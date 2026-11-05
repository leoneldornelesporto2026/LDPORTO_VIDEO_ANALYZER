# P0-03 - Origem de video guiada

Branch: develop. Base: 749a5bfd5dbe88afe8eb0a65f751982e8e6b2555.
Entrega: painel de origem separado, selecao de arquivo e acesso ao campo URL;
verificacao visivel e area de status; download opt-in sempre visivel.
Original local e SHA256 continuam presentes, mas recolhidos por padrao.
Os callbacks e o processamento continuam os mesmos: App -> analyze.py.
Nenhum modelo, GPU, download ou pacote foi executado para esta entrega.

## Gates Windows

- [x] 8/8 testes P0-03 PASS no Windows (commit c9c76a6, 2026-11-05).
- [x] 6/6 P0-02 e 15/15 P0-01 PASS (Windows 2026-11-05).
- [x] Regressao focal GUI 39 passed e 14 subtests passed (Windows 2026-11-05).
- [ ] Janela: launcher confirma Python 3.11.9; ainda faltam captura e clique em escolher video, URL, verificar, expandir/recolher.
- [ ] Consentimento permanece desmarcado por padrao e nao ocorre download automatico.
- [ ] Rodape fixo e scroll testados com diferentes escalas Windows.

Comandos: git pull --ff-only origin develop;
python -m unittest discover -s src/tests -p test_p0_media_card.py -v;
scripts/windows/testing/VALIDAR_P0_GUI.ps1; ABRIR_ANALYZER.bat.

Suite historica ainda bloqueada pelos dois ZIPs R4.9-S4 ausentes.
Sem homologacao de release ou main.
