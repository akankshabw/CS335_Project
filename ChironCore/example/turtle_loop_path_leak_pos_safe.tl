:out = 0
repeat :n [
  forward :pub + :secret
  backward :secret
  :out = :out + :pub
]
