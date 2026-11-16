/* Miam Démo — catalogue FICTIF (restaurants, plats et prix inventés). */
var RESTAURANTS = [
  { id: "bella", nom: "Bella Notte", categorie: "Pizza", note: 4.6, delai: 30, livraison: 2.49, minimum: 12,
    description: "Pizzas au feu de bois et pâtes fraîches",
    menu: [
      { section: "Pizzas", plats: [
        { id: "bella-marg", nom: "Pizza margherita", desc: "Tomate, mozzarella, basilic", prix: 10.5, options: "taillePizza" },
        { id: "bella-reine", nom: "Pizza reine", desc: "Tomate, mozzarella, jambon, champignons", prix: 12.9, options: "taillePizza" },
        { id: "bella-4f", nom: "Pizza quatre fromages", desc: "Mozzarella, gorgonzola, chèvre, parmesan", prix: 13.5, options: "taillePizza" },
        { id: "bella-veg", nom: "Pizza végétarienne", desc: "Poivrons, aubergine, courgette, olives", prix: 12.5, options: "taillePizza" }
      ]},
      { section: "Pâtes", plats: [
        { id: "bella-carbo", nom: "Spaghetti carbonara", desc: "Crème, lardons, parmesan", prix: 11.9 },
        { id: "bella-pesto", nom: "Penne au pesto", desc: "Basilic, pignons, parmesan", prix: 10.9 }
      ]},
      { section: "Desserts et boissons", plats: [
        { id: "bella-tira", nom: "Tiramisu maison", desc: "Mascarpone, café", prix: 5.5 },
        { id: "bella-eau", nom: "Eau pétillante 50 cl", desc: "", prix: 2.5 }
      ]}
    ]},
  { id: "smash", nom: "Smash Corner", categorie: "Burger", note: 4.4, delai: 25, livraison: 1.99, minimum: 10,
    description: "Burgers smashés et frites maison",
    menu: [
      { section: "Burgers", plats: [
        { id: "smash-classic", nom: "Smash classic", desc: "Double steak, cheddar, oignons, sauce maison", prix: 11.5, options: "burger" },
        { id: "smash-chicken", nom: "Crispy chicken", desc: "Poulet pané, salade, sauce piquante", prix: 10.9, options: "burger" },
        { id: "smash-veggie", nom: "Veggie smash", desc: "Galette de légumes, cheddar, tomate", prix: 10.5, options: "burger" }
      ]},
      { section: "Accompagnements", plats: [
        { id: "smash-frites", nom: "Frites maison", desc: "", prix: 3.5 },
        { id: "smash-onion", nom: "Onion rings", desc: "", prix: 4.2 }
      ]},
      { section: "Boissons", plats: [
        { id: "smash-cola", nom: "Soda 33 cl", desc: "", prix: 2.5 },
        { id: "smash-shake", nom: "Milkshake vanille", desc: "", prix: 4.9 }
      ]}
    ]},
  { id: "sakura", nom: "Sakura Box", categorie: "Asiatique", note: 4.7, delai: 35, livraison: 2.99, minimum: 15,
    description: "Sushis, makis et bols japonais",
    menu: [
      { section: "Plateaux", plats: [
        { id: "sakura-mix", nom: "Plateau mixte 18 pièces", desc: "Sushis, makis, california", prix: 19.9 },
        { id: "sakura-saumon", nom: "Plateau saumon 12 pièces", desc: "Sushis et makis saumon", prix: 15.9 }
      ]},
      { section: "Bols", plats: [
        { id: "sakura-poke", nom: "Poké saumon", desc: "Riz, saumon, avocat, edamame", prix: 13.5, options: "poke" },
        { id: "sakura-ramen", nom: "Ramen poulet", desc: "Bouillon, nouilles, œuf, poulet", prix: 12.9 }
      ]},
      { section: "Desserts", plats: [
        { id: "sakura-mochi", nom: "Mochis (3 pièces)", desc: "Mangue, matcha, coco", prix: 5.9 }
      ]}
    ]},
  { id: "thai", nom: "Bangkok Street", categorie: "Asiatique", note: 4.3, delai: 30, livraison: 2.49, minimum: 12,
    description: "Cuisine thaïe de rue",
    menu: [
      { section: "Plats", plats: [
        { id: "thai-padthai", nom: "Pad thaï crevettes", desc: "Nouilles de riz, cacahuètes, citron vert", prix: 12.5, options: "epice" },
        { id: "thai-curry", nom: "Curry vert poulet", desc: "Lait de coco, basilic thaï, riz", prix: 12.9, options: "epice" },
        { id: "thai-tofu", nom: "Tofu sauté aux légumes", desc: "Sauce soja, riz jasmin", prix: 11.5, options: "epice" }
      ]},
      { section: "Entrées", plats: [
        { id: "thai-nems", nom: "Nems au porc (4)", desc: "Salade, menthe, sauce", prix: 5.9 }
      ]}
    ]},
  { id: "verde", nom: "Verde Bowl", categorie: "Healthy", note: 4.5, delai: 20, livraison: 1.49, minimum: 10,
    description: "Salades, bols et jus frais",
    menu: [
      { section: "Salades et bols", plats: [
        { id: "verde-cesar", nom: "Salade César", desc: "Poulet, parmesan, croûtons", prix: 11.5 },
        { id: "verde-buddha", nom: "Buddha bowl", desc: "Quinoa, patate douce, houmous, avocat", prix: 12.5 },
        { id: "verde-falafel", nom: "Bol falafel", desc: "Falafels, taboulé, sauce yaourt", prix: 11.9 }
      ]},
      { section: "Jus", plats: [
        { id: "verde-jus", nom: "Jus pomme-gingembre", desc: "Pressé du jour", prix: 4.5 }
      ]}
    ]},
  { id: "douceur", nom: "La Petite Douceur", categorie: "Desserts", note: 4.8, delai: 25, livraison: 1.99, minimum: 8,
    description: "Pâtisseries et viennoiseries",
    menu: [
      { section: "Pâtisseries", plats: [
        { id: "douceur-tarte", nom: "Tarte au citron", desc: "Meringuée", prix: 4.9 },
        { id: "douceur-eclair", nom: "Éclair au chocolat", desc: "", prix: 3.9 },
        { id: "douceur-cookie", nom: "Cookies (lot de 3)", desc: "Chocolat, noisette", prix: 5.5 }
      ]}
    ]}
];

/* Groupes d'options. "requis" = un choix obligatoire (radio). Sinon cases à cocher. */
var OPTIONS = {
  taillePizza: [
    { titre: "Taille", requis: true, choix: [
      { id: "m", nom: "Moyenne (29 cm)", prix: 0 }, { id: "l", nom: "Grande (33 cm)", prix: 3 } ] },
    { titre: "Suppléments", requis: false, choix: [
      { id: "fro", nom: "Supplément fromage", prix: 1.5 }, { id: "oeuf", nom: "Œuf", prix: 1 } ] }
  ],
  burger: [
    { titre: "Cuisson", requis: true, choix: [
      { id: "ap", nom: "À point", prix: 0 }, { id: "bc", nom: "Bien cuit", prix: 0 } ] },
    { titre: "Formule", requis: false, choix: [
      { id: "menu", nom: "En menu (frites + boisson)", prix: 4.5 }, { id: "bacon", nom: "Bacon", prix: 1.5 } ] }
  ],
  poke: [
    { titre: "Base", requis: true, choix: [
      { id: "riz", nom: "Riz vinaigré", prix: 0 }, { id: "quinoa", nom: "Quinoa", prix: 0.5 } ] }
  ],
  epice: [
    { titre: "Niveau d'épices", requis: true, choix: [
      { id: "doux", nom: "Doux", prix: 0 }, { id: "moyen", nom: "Moyen", prix: 0 }, { id: "fort", nom: "Fort", prix: 0 } ] }
  ]
};

var FRAIS_SERVICE = 0.99;

if (typeof module !== "undefined") module.exports = { RESTAURANTS: RESTAURANTS, OPTIONS: OPTIONS, FRAIS_SERVICE: FRAIS_SERVICE };
