def normalize_result(result):
    """
    Normaliza o retorno de qualquer teste para 0 ou 1.
    """
    if result is None:
        return 0
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, (str, bytes)):
        return 1 if len(result) > 0 else 0
    return int(bool(result))
