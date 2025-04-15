import numpy as np
 
# Lê os sinais de referência e o sinal desconhecido como arrays NumPy
sinal_ref1 = np.array(list(map(int, input().split())))
sinal_ref2 = np.array(list(map(int, input().split())))
sinal_desconhecido = np.array(list(map(int, input().split())))
 
# Calcula a correlação com os sinais de referência
correlacao_ref1 = np.correlate(sinal_desconhecido, sinal_ref1, mode='same')
correlacao_ref2 = np.correlate(sinal_desconhecido, sinal_ref2, mode='same')
 
# Encontra o valor máximo de correlação
max_correlacao_ref1 = max(correlacao_ref1)
max_correlacao_ref2 = max(correlacao_ref2)
 
# Encontra o maior elemento de sinal_ref1 e sinal_ref2
maior_elemento_sinal_ref1 = max(sinal_ref1)
maior_elemento_sinal_ref2 = max(sinal_ref2)
 
# Divide max_correlacao_ref1 pelo maior elemento de sinal_ref1
max_correlacao_ref1 /= maior_elemento_sinal_ref1
 
# Divide max_correlacao_ref2 pelo maior elemento de sinal_ref2
max_correlacao_ref2 /= maior_elemento_sinal_ref2
 
print(f"correlacao com a referencia 1 = {max_correlacao_ref1}")
print(f"correlacao com a referencia 2 = {max_correlacao_ref2}")
 
if max_correlacao_ref1 > max_correlacao_ref2:
    print(f"referencia 1")
else:
    print(f"referencia 2")