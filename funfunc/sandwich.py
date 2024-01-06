import random

# Sandwich ingredients
breads = ['white bread', 'whole wheat', 'rye','sourdough','baguette','pumpernickel','ciabatta','multigrain','focaccia','bao']
proteins = ['turkey', 'chicken', 'ham', 'tofu', 'tempeh', 'bacon', 'roast beef', 'duck', 'salted egg', 'prawn', 'fish tempura']
cheeses = ['cheddar', 'swiss', 'gouda', 'mozzarella', 'provolone', 'blue cheese', 'feta', 'camembert', 'havarti']  # But you know how I feel about cheese.
veggies = ['lettuce', 'tomato', 'cucumber', 'onion', 'spinach', 'radish', 'pickled vegetables', 'avocado', 'roasted bell peppers', 'alfalfa sprouts']
condiments = ['mayo', 'mustard', 'aioli', 'hummus', 'vinaigrette', 'sriracha', 'hoisin sauce', 'Sichuan peppercorn oil', 'soy sauce', 'ginger-scallion sauce']

def make_random_sandwich():
    bread = random.choice(breads)
    protein = random.choice(proteins)
    cheese = random.choice(cheeses)
    veggie = random.choice(veggies)
    condiment = random.choice(condiments)
    
    sandwich = f"A delicious sandwich with {bread}, {protein}, {cheese}, {veggie}, and a touch of {condiment}."
    return sandwich

if __name__ == "__main__":
    print(make_random_sandwich())