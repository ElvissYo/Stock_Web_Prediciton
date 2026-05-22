from kag.market_data.stock_universe import (
    DEFAULT_SECTOR,
    StockUniverseRecord,
    parse_stockanalysis_idx_html,
    write_stock_universe_csv,
)


def test_parse_stockanalysis_idx_html_extracts_records_and_next_url():
    html = """
    <html>
      <head><link rel="next" href="/list/indonesia-stock-exchange/?page=2"></head>
      <body>
        <table id="main-table">
          <tbody>
            <tr>
              <td>1</td>
              <td class="sym"><a href="/quote/idx/BBCA/">BBCA</a></td>
              <td class="slw">PT Bank Central Asia Tbk</td>
              <td>724.97T</td>
            </tr>
            <tr>
              <td>2</td>
              <td class="sym"><a href="/quote/idx/TLKM/">TLKM</a></td>
              <td class="slw">Perusahaan Perseroan PT Telekomunikasi Indonesia Tbk</td>
              <td>289.24T</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    records, next_url = parse_stockanalysis_idx_html(
        html,
        base_url="https://stockanalysis.com/list/indonesia-stock-exchange/",
    )

    assert records == [
        StockUniverseRecord(
            ticker="BBCA",
            name="PT Bank Central Asia Tbk",
            universe_rank=1,
            sector=DEFAULT_SECTOR,
            exchange="IDX",
            yfinance_symbol="BBCA.JK",
        ),
        StockUniverseRecord(
            ticker="TLKM",
            name="Perusahaan Perseroan PT Telekomunikasi Indonesia Tbk",
            universe_rank=2,
            sector=DEFAULT_SECTOR,
            exchange="IDX",
            yfinance_symbol="TLKM.JK",
        ),
    ]
    assert next_url == "https://stockanalysis.com/list/indonesia-stock-exchange/?page=2"


def test_write_stock_universe_csv_outputs_ingestion_columns(tmp_path):
    csv_path = tmp_path / "idx_stock_universe.csv"

    rows_written = write_stock_universe_csv(
        [
            StockUniverseRecord(
                ticker="bbri",
                name="PT Bank Rakyat Indonesia (Persero) Tbk",
            )
        ],
        csv_path,
    )

    assert rows_written == 1
    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "ticker,name,sector,exchange,yfinance_symbol,universe_rank",
        "BBRI,PT Bank Rakyat Indonesia (Persero) Tbk,UNKNOWN,IDX,BBRI.JK,",
    ]
