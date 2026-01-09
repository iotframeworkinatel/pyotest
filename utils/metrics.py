import json

def save_metrics(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
