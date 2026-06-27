import urllib.request
from threading import Thread

from anamnesis.agent.graph_server import make_graph_server


def test_serves_files_from_directory(tmp_path):
    (tmp_path / "cluster_x.html").write_text("<html>hi</html>", encoding="utf-8")
    server = make_graph_server(str(tmp_path), 0)  # port 0 -> OS-assigned ephemeral port
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/cluster_x.html", timeout=5).read()
        assert b"hi" in body
    finally:
        server.shutdown()
        server.server_close()


def test_creates_missing_directory(tmp_path):
    target = tmp_path / "graphs"
    server = make_graph_server(str(target), 0)
    try:
        assert target.is_dir()
    finally:
        server.server_close()
