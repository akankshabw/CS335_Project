:out = 0
if :pub > 0 [
  if :pub > 10 [
    if :secret > 5 [
      :out = :pub
    ] else [
      :out = :pub
    ]
  ] else [
    :out = :pub + 1
  ]
] else [
  :out = 0 - :pub
]