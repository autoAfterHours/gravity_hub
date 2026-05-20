orbit_input_handler = None

def request_input(fields):
    if orbit_input_handler is None:
        raise Exception("Orbit input handler not registered")
    return orbit_input_handler(fields)

