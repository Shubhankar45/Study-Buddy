eventlet.monkey_patch()
from app import app, socketio
import eventlet
  # needed if using eventlet

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False
    )
