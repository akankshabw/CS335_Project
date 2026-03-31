:out = 0
:acc = :secret * 2
:mask = :secret
@@ :out
@@ :acc - :mask - :mask
repeat :n [
  :acc = :acc + :pub * 2
  :mask = :mask + :pub
  :out = :out + :acc - :mask - :mask
]