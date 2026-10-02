from gamefunc.minecraft_events import _classify

_PREFIX = '[19:30:01] [Server thread/INFO]: '


def test_player_death_reported():
    assert _classify(_PREFIX + 'Knova1 fell out of the world') == 'Knova1 fell out of the world'
    assert _classify(_PREFIX + 'Ventoz was slain by Zombie') == 'Ventoz was slain by Zombie'


def test_villager_death_ignored():
    line = (_PREFIX + "Villager Villager['Villager'/13665, l='ServerLevel[world]', "
            "x=588.70, y=74.00, z=322.50] died, message: 'Villager was killed'")
    assert _classify(line) is None


def test_profession_villager_death_ignored():
    line = (_PREFIX + "Villager Villager['Farmer'/13681, l='ServerLevel[world]', "
            "x=567.54, y=111.00, z=370.71] died, message: "
            "'Farmer was obliterated by a sonically-charged shriek'")
    assert _classify(line) is None


def test_named_pet_death_ignored():
    line = (_PREFIX + "Named entity Wolf['Rex'/412, l='ServerLevel[world]', "
            "x=1.50, y=64.00, z=2.50] died, message: 'Rex was slain by Skeleton'")
    assert _classify(line) is None
