"""Bounded fixed request contract shared by the panel and its worker."""
MAX_REQUEST = 4 * 1024 * 1024
MAX_STATUS = 32 * 1024 * 1024
FIELDS = {
    "prepare": {"source", "object_name", "output", "blender"},
    "plan": {"base", "left", "right", "output", "blender"},
    "resume": {"base", "left", "right", "document"},
    "inspect": {"review", "output", "decisions", "blender"},
    "apply": {"review", "output", "decisions", "blender", "accept_scope"},
    "serve": {"folder"},
}


def validate_request(action, args):
    if type(action) is not str or action not in FIELDS or type(args) is not dict or set(args) != FIELDS[action]:
        raise ValueError("Invalid workflow action or arguments")
    for key, value in args.items():
        if key == "accept_scope":
            if type(value) is not bool:
                raise ValueError("Scope acceptance must be explicit")
        elif key == "decisions" and value is None:
            continue
        elif type(value) is not str or not value or len(value) > 4096 or "\0" in value:
            raise ValueError("Invalid workflow argument: " + key)
