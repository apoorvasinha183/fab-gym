"""The agent loop (docs/AGENT.md). Tests first: declared, not yet built."""


class StandInModel:
    def __init__(self, replies):
        raise NotImplementedError

    def complete(self, messages):
        raise NotImplementedError


class HttpModel:
    def __init__(self, base_url, model, key_file):
        raise NotImplementedError


class Scorer:
    def __init__(self, cli, shop, train, threads=4, scenario=None):
        raise NotImplementedError


def search(question, model, scorer, generations=3, per_generation=2):
    raise NotImplementedError


def finalise(s, scorer, top=2, out_dir=None):
    raise NotImplementedError


def sign(card_path, name):
    raise NotImplementedError
