:out = 0
repeat :n [
  if :pub > 5 [
    :out = :out + 2
  ] else [
    :out = :out + 1
  ]
]