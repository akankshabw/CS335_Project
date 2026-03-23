:out = 0
repeat :n [
  forward :pub
  right 90
  forward :secret * 80
  left 90
  forward :pub
  left 90
  forward :secret * 80
  right 90
  :out = :out + 1
]
