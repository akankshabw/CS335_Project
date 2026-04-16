:out = 0
:flag = 0
@@ :out
@@ :flag
repeat :n [
  :flag = :flag + :secret
  :out = :out + :pub
]
@@ :out
repeat :n [
  :out = :out + :flag
]
