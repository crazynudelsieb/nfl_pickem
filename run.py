# Eventlet monkey patching MUST be first before any other imports
import eventlet
eventlet.monkey_patch()

from app import create_app, db
from app.models import Game, Group, Pick, Season, Team, User

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "User": User,
        "Group": Group,
        "Game": Game,
        "Pick": Pick,
        "Season": Season,
        "Team": Team,
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
