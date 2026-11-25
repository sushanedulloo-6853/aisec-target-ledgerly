import base64
import io
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# the model sometimes adds imports even though plt/data are already provided
_IMPORT_LINE = re.compile(r"^\s*(import|from)\s+\S+.*$", re.MULTILINE)


def render_chart(code: str, data: list[dict], title: str | None = None) -> str:
    """Run model-written plotting code against `data` and return a base64 PNG."""
    code = _IMPORT_LINE.sub("", code)
    plt.close("all")
    fig = plt.figure(figsize=(8, 4.5))
    scope = {"plt": plt, "fig": fig, "data": data, "title": title}
    exec(code, scope)
    if title:
        plt.title(title)
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", dpi=110)
    plt.close("all")
    return base64.b64encode(buf.getvalue()).decode()
