from web.framework import app


@app.route("/status")
def status():
    return {"ok": True}
