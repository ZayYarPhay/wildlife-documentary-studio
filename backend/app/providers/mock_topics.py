from typing import Any

from app.providers.base import TopicSuggestionProvider

CATALOG: dict[str, list[dict[str, Any]]] = {
    "MAMMALS": [
        {
            "topic": "African elephant",
            "scientific_name": "Loxodonta africana",
            "hook": "Follow the family bonds and long memory of the largest land animal.",
            "stock_score": 95,
        },
        {
            "topic": "Red fox",
            "scientific_name": "Vulpes vulpes",
            "hook": "Explore how an adaptable hunter thrives from wild forests to city edges.",
            "stock_score": 90,
        },
        {
            "topic": "Japanese macaque",
            "scientific_name": "Macaca fuscata",
            "hook": "Enter a snowy world where primates survive winter through cooperation and learning.",
            "stock_score": 78,
        },
        {
            "topic": "Giant anteater",
            "scientific_name": "Myrmecophaga tridactyla",
            "hook": "Reveal the specialized senses and astonishing feeding life of a grassland giant.",
            "stock_score": 62,
        },
    ],
    "BIRDS": [
        {
            "topic": "Barn owl",
            "scientific_name": "Tyto alba",
            "hook": "Discover the silent flight and extraordinary hearing of a nocturnal hunter.",
            "stock_score": 91,
        },
        {
            "topic": "Emperor penguin",
            "scientific_name": "Aptenodytes forsteri",
            "hook": "Cross Antarctic winter with parents enduring one of nature's hardest breeding cycles.",
            "stock_score": 88,
        },
        {
            "topic": "Greater flamingo",
            "scientific_name": "Phoenicopterus roseus",
            "hook": "Trace the food, color and social displays behind vast pink colonies.",
            "stock_score": 82,
        },
        {
            "topic": "Shoebill",
            "scientific_name": "Balaeniceps rex",
            "hook": "Meet a patient wetland ambush hunter with an unmistakable prehistoric silhouette.",
            "stock_score": 55,
        },
    ],
    "REPTILES": [
        {
            "topic": "Komodo dragon",
            "scientific_name": "Varanus komodoensis",
            "hook": "Walk the dry islands ruled by the world's largest living lizard.",
            "stock_score": 81,
        },
        {
            "topic": "Green sea turtle",
            "scientific_name": "Chelonia mydas",
            "hook": "Follow an ocean traveler returning across great distances to its natal shore.",
            "stock_score": 89,
        },
        {
            "topic": "Nile crocodile",
            "scientific_name": "Crocodylus niloticus",
            "hook": "Watch an ancient predator shape life at the water's edge.",
            "stock_score": 92,
        },
        {
            "topic": "Thorny devil",
            "scientific_name": "Moloch horridus",
            "hook": "Uncover the remarkable water-harvesting adaptations of a desert specialist.",
            "stock_score": 48,
        },
    ],
    "OCEAN": [
        {
            "topic": "Humpback whale",
            "scientific_name": "Megaptera novaeangliae",
            "hook": "Journey with a singing giant through migration, feeding and calf-rearing seas.",
            "stock_score": 94,
        },
        {
            "topic": "Giant Pacific octopus",
            "scientific_name": "Enteroctopus dofleini",
            "hook": "Explore intelligence, camouflage and a brief but astonishing life beneath the kelp.",
            "stock_score": 72,
        },
        {
            "topic": "Manta ray",
            "scientific_name": "Mobula birostris",
            "hook": "Glide beside a gentle ocean traveler at cleaning stations and feeding gatherings.",
            "stock_score": 75,
        },
        {
            "topic": "Leafy seadragon",
            "scientific_name": "Phycodurus eques",
            "hook": "Find a master of disguise drifting through southern Australian seagrass.",
            "stock_score": 45,
        },
    ],
    "INSECTS": [
        {
            "topic": "Monarch butterfly",
            "scientific_name": "Danaus plexippus",
            "hook": "Follow a multi-generational migration spanning a continent.",
            "stock_score": 86,
        },
        {
            "topic": "Leafcutter ant",
            "scientific_name": "Atta cephalotes",
            "hook": "Enter an underground farming society built on fungus and collective labor.",
            "stock_score": 67,
        },
        {
            "topic": "European honey bee",
            "scientific_name": "Apis mellifera",
            "hook": "Decode dances, division of labor and the pollination network around a hive.",
            "stock_score": 93,
        },
        {
            "topic": "Orchid mantis",
            "scientific_name": "Hymenopus coronatus",
            "hook": "See how flower-like camouflage becomes a predator's deceptive advantage.",
            "stock_score": 51,
        },
    ],
    "RARE_ANIMALS": [
        {
            "topic": "Saola",
            "scientific_name": "Pseudoryx nghetinhensis",
            "hook": "Investigate one of the world's least-seen large mammals and the forests it needs.",
            "stock_score": 18,
        },
        {
            "topic": "Kakapo",
            "scientific_name": "Strigops habroptilus",
            "hook": "Meet a flightless nocturnal parrot whose recovery depends on intensive conservation.",
            "stock_score": 42,
        },
        {
            "topic": "Amur leopard",
            "scientific_name": "Panthera pardus orientalis",
            "hook": "Track a cold-forest cat returning from the edge of extinction.",
            "stock_score": 39,
        },
        {
            "topic": "Aye-aye",
            "scientific_name": "Daubentonia madagascariensis",
            "hook": "Reveal the unusual nighttime foraging tools of Madagascar's elusive lemur.",
            "stock_score": 36,
        },
    ],
    "PREDATORS": [
        {
            "topic": "Snow leopard",
            "scientific_name": "Panthera uncia",
            "hook": "Climb into thin mountain air with a solitary hunter built for cliffs and cold.",
            "stock_score": 71,
        },
        {
            "topic": "Orca",
            "scientific_name": "Orcinus orca",
            "hook": "Compare the learned hunting cultures of the ocean's powerful family groups.",
            "stock_score": 87,
        },
        {
            "topic": "Cheetah",
            "scientific_name": "Acinonyx jubatus",
            "hook": "Balance explosive speed against the daily risks faced by a specialized hunter.",
            "stock_score": 94,
        },
        {
            "topic": "Harpy eagle",
            "scientific_name": "Harpia harpyja",
            "hook": "Rise into rainforest canopy territory with one of the world's strongest eagles.",
            "stock_score": 58,
        },
    ],
}


class MockTopicSuggestionProvider(TopicSuggestionProvider):
    name = "mock"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def suggest(
        self, category: str, excluded_topics: list[str], count: int, **options: Any
    ) -> list[dict[str, Any]]:
        excluded = {item.casefold() for item in excluded_topics}
        candidates = [dict(item) for item in CATALOG[category]]
        fresh = [item for item in candidates if item["topic"].casefold() not in excluded]
        used = [item for item in candidates if item["topic"].casefold() in excluded]
        return (fresh + used)[:count]
