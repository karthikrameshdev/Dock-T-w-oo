"""Reviewed character roster; appearance is authored here, never randomized."""
# id, display name, family, species/profession, main, secondary, accent, scale
ROWS = [
('default','Brain','robot','default','#268AC2','#E4ECEF','#47E5FF',1.0),
('orbit','Orbit','robot','orbital','#7453C6','#ECE8FA','#71FFF0',1.0),
('ember','Ember','robot','rescue','#E45E38','#F9E9CF','#FFD159',1.0),
('mint','Mint','robot','medic','#36A48E','#EDF7EB','#8AFFD0',.97),
('cosmo','Cosmo','robot','space','#244E88','#DDE7F7','#92B5FF',1.03),
('pixel','Pixel','robot','retro','#D5AD48','#314A5C','#A8FFC3',.93),
('corgi','Biscuit','quadruped','corgi','#CE8747','#FFF0D3','#4BDCD5',.82),
('beagle','Scout','quadruped','beagle','#A3673B','#F3E4CA','#FFA95E',.90),
('husky','Frost','quadruped','husky','#708798','#F2F4EF','#73DDFC',.96),
('tuxedo','Tux','quadruped','tuxedo','#283943','#EBF3EC','#9DE4BD',.78),
('calico','Patches','quadruped','calico','#E7D5B4','#CF7D40','#F9A6CC',.77),
('siamese','Mochi','quadruped','siamese','#D6C7AC','#584C51','#8CBAFF',.80),
('owl','Luma','bird','owl','#9A7160','#F1DEB8','#FFD188',.82),
('parrot','Rio','bird','parrot','#3EAD9B','#FFD363','#FF776E',.84),
('robin','Pip','bird','robin','#588A9B','#DF865F','#8AF0E8',.68),
('rat','Remy','quadruped','rat','#8992A4','#D8CDDC','#F3B6E1',.48),
('mouse','Pebble','quadruped','mouse','#C4B4A3','#F7EADB','#B8DDFB',.42),
('lion','Leo','quadruped','lion','#DBA14E','#9F5F31','#FFDD65',1.0),
('tiger','Tango','quadruped','tiger','#E3983D','#3F3D3C','#A9F4E6',1.0),
('fox','Fable','quadruped','fox','#C96E40','#F5E5C6','#70E1CF',.85),
('rabbit','Clover','quadruped','rabbit','#EBDFCD','#D6A3B7','#B0EAA3',.70),
('panda','Bao','quadruped','panda','#F0EDE3','#36424B','#B2E2A6',.94),
('elephant','Nori','quadruped','elephant','#83A1AE','#BFCBD0','#F8C788',1.02),
('red_panda','Maple','quadruped','red_panda','#AC5942','#F0D9AE','#FFE38B',.85),
('astronaut','Nova','human','astronaut','#D9E4EC','#437AB5','#8DDFFF',1.0),
('scientist','Ada','human','scientist','#F2EDE2','#5B9D9A','#C5FAAD',.98),
('artist','Indigo','human','artist','#536CC3','#DFAC67','#F9A0C2',.96),
('chef','Saffron','human','chef','#EEE8D9','#C35C44','#FFD890',.98),
('explorer','Kai','human','explorer','#52857A','#D6AF6E','#BDF0CF',1.02),
('musician','Zuri','human','musician','#A35993','#335576','#A9EEFF',.97),
]
ROSTER=[dict(zip(('id','name','family','species','main','secondary','accent','scale'),row),index=i) for i,row in enumerate(ROWS)]
SKINS={'astronaut':'#B87E59','scientist':'#E4B68C','artist':'#CA916B','chef':'#F0C5A0','explorer':'#A96F4D','musician':'#76503D'}
HAIR={'astronaut':'#372D30','scientist':'#343440','artist':'#6C3D36','chef':'#654B38','explorer':'#302C29','musician':'#282327'}
