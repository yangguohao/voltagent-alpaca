from ai_agent.signals.volatility import VolatilitySignalGenerator

def _make_bars(n, base=100.0):
    bars, price = [], base
    for i in range(n):
        price *= 1 + (0.001 if i % 2 == 0 else -0.0008)
        bars.append({"close": price})
    return bars

def test_volatility_signal_generates():
    signal = VolatilitySignalGenerator().generate("SPY", bars=_make_bars(100))
    assert signal is not None
    assert signal.symbol == "SPY"
    assert "iv_rank" in signal.metadata

def test_volatility_signal_insufficient_data():
    assert VolatilitySignalGenerator().generate("SPY", bars=_make_bars(10)) is None
