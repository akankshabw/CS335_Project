:out = 0
:acc = :secret + :pub
@@ :out
@@ :acc - :secret
repeat :n [
  :out = :out + :acc
  :acc = :acc + :pub
]