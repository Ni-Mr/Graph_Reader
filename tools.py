import datetime
import json
import os
import re
import time
import matplotlib
import networkx as nx
import openai
from langchain_openai import ChatOpenAI
from matplotlib import pyplot as plt
from nltk import PorterStemmer

from template import Graph_Construction, exploring_atomic_facts, Chunk_Read, exploring_chunks, exploring_neighbors, \
    answer_reasoning

matplotlib.use("TkAgg")
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_API_BASE"] = ""
gpt_client = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0.1)


def data_sample():
    with open("dataset.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data_iterator = iter(data)
    return data_iterator


def query_model(
        prompt: str,
        seconds_to_reset_tokens: float = 30.0,
) -> str:
    while True:
        try:
            raw_response = gpt_client.invoke(prompt)
            return raw_response.content.strip()
        except openai.RateLimitError as e:
            print(f'{datetime.datetime.now()}: query_gpt_model: RateLimitError {e.message}: {e}')
            time.sleep(seconds_to_reset_tokens)
        except openai.APIError as e:
            print(f'{datetime.datetime.now()}: query_gpt_model: APIError {e.message}: {e}')
            print(f'{datetime.datetime.now()}: query_gpt_model: Retrying after 5 seconds...')
            time.sleep(5)


def context_process(example, split_size, view=False):
    context_map = {}
    for i, j in enumerate(range(0, len(example['context']), split_size)):
        context_map[f"Chunk_ID_{i}"] = example['context'][j:j + split_size]
    facts_ls = []
    stemmer = PorterStemmer()
    for k, v in zip(context_map.keys(), context_map.values()):
        query = Graph_Construction.format(v)
        response = query_model(prompt=query)
        for i in response.strip().split('\n'):
            tmp_ls = []
            key_ls = set()
            for j in i.split('|')[1:]:
                j = j.strip().lower()
                j = re.sub(r'[^a-zA-Z\d]', ' ', j)
                j = stemmer.stem(j)
                key_ls.add(j.strip().lower())
            tmp_ls.append(key_ls)
            tmp_ls.append((k, i.split('|')[0]))
            facts_ls.append(tmp_ls)
    key_set = set()
    for i in facts_ls:
        key_set |= i[0]
    node_set = {}
    for i in key_set:
        node_set[i] = set()
        for j in facts_ls:
            if i in j[0]:
                node_set[i].add(j[1])
    # 这里缺少一步处理：关键词的语义聚合、关联聚合
    G = nx.Graph()
    for word1 in node_set.keys():
        for word2 in node_set.keys():
            if word1 != word2:
                if not node_set[word1].isdisjoint(node_set[word2]):
                    G.add_edge(word1, word2)
    if view:
        # 可视化图谱
        pos = nx.spring_layout(G, iterations=100, k=1)
        plt.figure(figsize=(12, 6))
        nx.draw(G, pos, with_labels=True, node_size=200, node_color='skyblue', font_size=10, edge_color='gray')
        plt.show()
    return context_map, node_set, G


def explore_atomic_facts(node_name, node_set, history):
    if node_name in node_set.keys():
        node_facts = node_set[node_name]
        response = f"Node: {node_name}; "
        actions = f"Exploring Atomic Facts Node: {node_name}; ["
        for item in node_facts:
            response += f"[{item[1]} from {item[0]}]"
            ID = item[1].split('.')[0].strip()
            actions += f"Atomic Fact {ID} from {item[0]}, "
        actions += "]"
    else:
        response = f"Node: {node_name} does not exist."
        actions = f"Exploring Atomic Facts Node: {node_name}, But node does not exist."
    query = history_process(history) + response + exploring_atomic_facts
    response = query_model(prompt=query)
    history["Previous actions"].append(actions)
    notebook = ''
    for i in response.split('*Rationale for Next Action*')[0].strip().split('\n')[1:]:
        notebook += '\n' + i.strip(' ')
    history["Notebook"] = notebook
    Chosen_Action = response.strip().split('\n')[-1].split(':')[-1].strip()
    answer = ''
    return Chosen_Action, history, answer


def history_process(history):
    response = ''
    for i in history.keys():
        response += i + ': ' + str(history[i]) + '\n'
    return response


# 探索窗口信息
def read_chunk(Chosen_Action, context_map, history):
    # 使用正则表达式匹配Chunk ID
    chunk_id_list = re.findall(r'\d+', Chosen_Action)

    def read(ID):
        if -1 < int(ID) < len(list(context_map.keys())):
            chunk_id = f"Chunk_ID_{ID}"
            query = Chunk_Read.format(context_map[chunk_id], history['Notebook'], history['Question'])
            response = query_model(prompt=query)
            summary = response.strip().split('\n')[0].split('[summary]')[-1].strip()
            history['Notebook'] += '\n- ' + summary
            history["Previous actions"].append(f"read_chunk({chunk_id})")
            if '[answerable]' in response:
                answers = response.strip().split('\n')[-1]
                Next_Action = ''
                return Next_Action, history, answers
            else:
                query = history_process(history) + exploring_chunks
                response = query_model(prompt=query)
                notebook = ''
                for i in response.split('*Rationale for Next Action*')[0].strip().split('\n')[1:]:
                    notebook += '\n' + i.strip(' ')
                history["Notebook"] = notebook
                Next_Action = response.strip().split('\n')[-1].split(':')[-1].strip()
                answers = ''
                return Next_Action, history, answers
        else:
            Next_Action = 'search_more()'
            answers = ''
            return Next_Action, history, answers

    index = 0
    current_chunk_id = int(chunk_id_list[index])
    Chosen_Action, history, answer = read(current_chunk_id)
    while True:
        if 'search_more' in Chosen_Action:
            index += 1
            if index < len(chunk_id_list):
                current_chunk_id = int(chunk_id_list[index])
                Chosen_Action, history, answer = read(current_chunk_id)
            else:
                return Chosen_Action, history, answer
        elif 'read_previous_chunk' in Chosen_Action:
            current_chunk_id -= 1
            Chosen_Action, history, answer = read(current_chunk_id)
        elif 'read_subsequent_chunk' in Chosen_Action:
            current_chunk_id += 1
            Chosen_Action, history, answer = read(current_chunk_id)
        elif 'termination' in Chosen_Action:
            return Chosen_Action, history, answer
        elif Chosen_Action == '':
            return Chosen_Action, history, answer


def read_neighbor_node(current_node, G, history):
    history["Previous actions"].append(f"Check the neighbor information of the node ({current_node}).")
    query = f"Current Node: {current_node}; Neighbor Nodes: {list(G.neighbors(current_node))}\n" + history_process(
        history) + exploring_neighbors
    response = query_model(prompt=query)
    if 'termination' in response:
        Chosen_Action = 'termination()'
        answer = ''
        return Chosen_Action, history, answer
    else:
        neighbor_node = response.strip().split('\n')[-1].split('(')[-1].split(')')[0].strip()
        Chosen_Action = f'explore_atomic_facts({neighbor_node})'
        return Chosen_Action, history, neighbor_node


def answer_reason(history):
    query = answer_reasoning.format(history['Question'], history['Notebook'])
    response = query_model(prompt=query)
    return response




