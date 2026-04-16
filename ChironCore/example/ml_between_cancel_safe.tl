:out = 0
:carry = 0
:k = 0
@@ :out
@@ :carry - :k
repeat :n [
  :carry = :carry + :pub
  :out = :out + :pub
  :k = :k + :pub
]
:carry = :carry + :secret
:k = :k + :secret
@@ :out
@@ :carry - :k
repeat :n [
  :out = :out + :carry - :k
]
