"""
GraphAdapter to Monarch graph API
"""
from typing import Optional, Any, List, Dict
from enum import Enum
import requests

# from bmt import Toolkit

from mta.services.config import config
from mta.services.util import (
    TERM_DATA,
    MATCH_LIST,
    RESULT_ENTRY,
    RESULTS_MAP,
    RESULT
)
from mta.services.util.logutil import LoggingUtil

logger = LoggingUtil.init_logging(
    __name__,
    config.get('logging_level'),
    config.get('logging_format'),
)

LATEST_BIOLINK_MODEL = "1.4.0"
MONARCH_SEMSIMIAN = "http://api-v3.monarchinitiative.org/v3/api/semsim/search"


class SemsimSearchCategory(Enum):
    HGNC = "Human Genes"
    MGI = "Mouse Genes"
    RGD = "Rat Genes"
    ZFIN = "Zebrafish Genes"
    WB = "C. Elegans Genes"
    MONDO = "Human Diseases"


def get_nested_tag_value(data: Dict, path: List[str], pos: int) -> Optional[Any]:
    """
    Navigate dot delimited tag 'path' into a multi-level dictionary, to return its associated value.

    :param data: Dict, multi-level data dictionary
    :param path: str, dotted JSON tag path
    :param pos: int, zero-based current position in tag path
    :return: string value of the multi-level tag, if available; 'None' otherwise if no tag value found in the path
    """
    tag = path[pos]
    part_tag_path = ".".join(path[:pos+1])
    if tag not in data:
        logger.debug(f"\tMissing tag path '{part_tag_path}'?")
        return None

    pos += 1
    if pos == len(path):
        return data[tag]
    else:
        return get_nested_tag_value(data[tag], path, pos)


def tag_value(json_data, tag_path) -> Optional[Any]:
    """
    Retrieve value of leaf in multi-level dictionary at
    the end of a specified dot delimited sequence of keys.
    :param json_data:
    :param tag_path:
    :return:
    """
    if not tag_path:
        logger.debug(f"\tEmpty 'tag_path' argument?")
        return None

    parts = tag_path.split(".")
    return get_nested_tag_value(json_data, parts, 0)


class MonarchInterface:
    """
    Singleton class for interfacing with the Monarch Initiative graph.
    """
    class _MonarchInterface:
        def __init__(self, query_timeout, bl_version=LATEST_BIOLINK_MODEL):
            self.schema = None
            # used to keep track of derived inverted predicates
            # self.inverted_predicates = defaultdict(lambda: defaultdict(set))
            self.query_timeout = query_timeout
            # self.toolkit = Toolkit()
            self.bl_version = bl_version

        # TODO: add useful _GraphInterface methods here!
        async def get_node(
                self,
                node_type: str,
                curie: str
        ) -> Dict:
            """
            Returns a node that matches curie as its ID.
            :param node_type: Type of the node.
            :type node_type:str
            :param curie: Curie.
            :type curie: str
            :return: Contents of the node in Monarch.
            :rtype: Dict
            """
            # TODO: Implement me!
            return dict()

        async def get_single_hops(self, source_type: str, target_type: str, curie: str) -> List:
            """
            Returns a triplets of source to target where source id is curie.
            :param source_type: Type of the source node.
            :type source_type: str
            :param target_type: Type of target node.
            :type target_type: str
            :param curie: Curie of source node.
            :type curie: str
            :return: List of triplets where each item contains source node, edge, target.
            :rtype: List
            """
            # TODO: Implement me!
            return list()

        @staticmethod
        async def semsim_search(
                identifiers: List[str],
                group: SemsimSearchCategory
        ) -> List[Dict]:
            """
            Generalized call to Monarch SemSim search endpoint.
            :param identifiers: list of identifiers to be matched.
            :param group: concept category targeted for matching.
            :return: List[Dict], of 'raw' SemSimian result objects
            """
            #
            # Example HTTP POST to SemSimian:
            #
            # curl -X 'POST' \
            #   'http://api-v3.monarchinitiative.org/v3/api/semsim/search' \
            #   -H 'accept: application/json' \
            #   -H 'Content-Type: application/json' \
            #   -d '{
            #   "termset": ["HP:0002104", "HP:0012378", "HP:0012378", "HP:0012378"],
            #   "group": "Human Diseases",
            #   "limit": 5
            # }'
            #
            query = {
              "termset": identifiers,
              "group": group.value,
              "limit": 5
            }
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }
            response = requests.post(
                MONARCH_SEMSIMIAN,
                json=query,
                headers=headers
            )

            if not response.status_code == 200:
                logger.error(
                    f"Monarch SemSimian at '\nUrl: '{MONARCH_SEMSIMIAN}', "
                    f"Query: '{query}' returned HTTP error code: '{response.status_code}'"
                )
                return list()

            return response.json()

        @staticmethod
        def parse_raw_semsim(
                full_result: List[Dict],
                match_category: str
        ) -> RESULTS_MAP:
            """
            Parse out the SemSimian matched object terms associated with specified subject ids.
            :param full_result: List[SemsimSearchResult], raw Semsimian result
            :param match_category: str, Biolink Model concept category of matched terms (not provided by SemSimian?)
            :return: RESULT_MAP, results indexed by matched subjects,
                                 with similarity profiles matching query inputs
            """
            result: RESULTS_MAP = dict()
            for entry in full_result:
                subject_id = tag_value(entry, "subject.id")
                result[subject_id]: RESULT_ENTRY = dict()
                subject_name = tag_value(entry, "subject.name")
                result[subject_id]["name"] = subject_name
                subject_category = tag_value(entry, "subject.category")
                result[subject_id]["category"] = subject_category
                object_termset: Dict = tag_value(entry, "similarity.object_termset")
                result[subject_id]["matches"]: MATCH_LIST = list()
                if object_termset:
                    for object_term in object_termset.values():
                        object_id = object_term["id"]
                        object_name = object_term["label"]
                        term_data: TERM_DATA = {
                            "id": object_id,
                            "name": object_name,
                            "category": match_category
                        }
                        result[subject_id]["matches"].append(term_data)
            return result

        async def phenotype_semsim_to_disease(self, phenotype_ids: List[str]) -> RESULT:
            """
            :param phenotype_ids: list of (HPO?) phenotype identifiers
            :type phenotype_ids: List[str]
            :return: Dictionary indexed by (MONDO) disease CURIEs, containing the name and category of
                     the MONDO term, plus lists of matching phenotype feature CURIEs with their name
            :rtype: RESULT_MAP
            """
            full_result: List[Dict] = await self.semsim_search(
                identifiers=phenotype_ids, group=SemsimSearchCategory.MONDO
            )
            result_map: RESULTS_MAP = self.parse_raw_semsim(
                full_result=full_result,
                match_category="biolink:PhenotypicFeature"
            )
            result: RESULT = dict()
            result["primary_knowledge_source"] = "infores:hpo-annotations"
            result["result_map"] = result_map
            return result

        async def run_query(self, identifiers: List[str]) -> RESULT:
            """
            Initial MVP is a single highly specialized query MVP use case against Monarch.
                 Sends an input list of (HPO-indexed) phenotypic feature CURIEs to a
                 Monarch Semantic Similarity search to match (MONDO-indexed) Diseases.
                 No scoring metrics or supporting evidence (yet) returned in this iteration.

            :param identifiers: Python dictionary version of query parameters
            :type identifiers: Dict
            :return: Dictionary of Monarch 'subject' identifier hits indexing Lists of matched input identifiers.
            :rtype: Dict[str, List[str]]
            """
            result: RESULT = await self.phenotype_semsim_to_disease(phenotype_ids=identifiers)
            return result

    instance = None

    def __init__(self, query_timeout=600, bl_version=LATEST_BIOLINK_MODEL):
        # create a new instance if not already created.
        if not MonarchInterface.instance:
            MonarchInterface.instance = MonarchInterface._MonarchInterface(
                query_timeout=query_timeout,
                bl_version=bl_version
            )

    def __getattr__(self, item):
        # proxy function calls to the inner object.
        return getattr(self.instance, item)
