:out = 0
:carry = 0
@@ :out
@@ :carry
repeat :n [
  :carry = :carry + :pub
  :out = :out + :pub
]
:carry = :carry + :secret
@@ :out
@@ :carry
repeat :n [
  :out = :out + :carry
]
