import random
import numpy as np
# import gymnasium as gym
# import time
# from gymnasium import spaces
# import os
import sklearn
import sklearn.pipeline
import sklearn.preprocessing
from sklearn.kernel_approximation import RBFSampler
import pickle


class VanillaFeatureEncoder:
    def __init__(self, env):
        self.env = env
        
    def encode(self, state):
        return state
    
    @property
    def size(self): 
        return self.env.observation_space.shape[0]

class RBFFeatureEncoder:
    def __init__(self, env, gamma=1.0, n_components=100):
        self.env = env
        self.gamma = gamma
        self.n_components = n_components
        self.sampler = RBFSampler(gamma=self.gamma, n_components=self.n_components, random_state=1)
        self.StandardScaler = sklearn.preprocessing.StandardScaler()
        
        #Generate sample data within the observation space and fit the sampler
        sample_data = []
        for _ in range(100):
            sample_data.append(env.observation_space.sample())

        sample_data = np.array(sample_data)

        self.StandartScaler = self.StandardScaler.fit(sample_data)
        sample_data = self.StandardScaler.transform(sample_data)

        self.sampler.fit(sample_data)
        
    def encode(self, state):
        #Transforming to 2D
        state = np.array(state).reshape(1, -1)
        #State normalization
        state = self.StandardScaler.transform(state)
        #Transform the state using the RBFSampler
        return self.sampler.transform(state).flatten()
    
    @property
    def size(self):
        return self.n_components

class TDLambda_LVFA:
    def __init__(self, env, feature_encoder_cls=RBFFeatureEncoder, alpha=0.01, alpha_decay=1, 
                 gamma=0.9999, epsilon=0.3, epsilon_decay=0.995, final_epsilon=0.2, lambda_=0.9): # modify if you want (e.g. for forward view)
        self.env = env
        self.feature_encoder = feature_encoder_cls(env)
        self.shape = (self.env.action_space.n, self.feature_encoder.size)
        self.weights = np.random.random(self.shape)
        self.traces = np.zeros(self.shape)
        self.alpha = alpha
        self.alpha_decay = alpha_decay
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.final_epsilon = final_epsilon
        self.lambda_ = lambda_
        
    def Q(self, feats):
        feats = feats.reshape(-1,1)
        return self.weights@feats
    
    def update_transition(self, s, action, s_prime, reward, done):
        s_feats = self.feature_encoder.encode(s)
        s_prime_feats = self.feature_encoder.encode(s_prime)
        q_s = self.Q(s_feats)
        q_s_prime = self.Q(s_prime_feats)
        #Calculating TD error
        td_error = reward + (not done)*self.gamma * np.max(q_s_prime) - q_s[action]

        #Update eligibility traces
        self.traces *= self.gamma * self.lambda_
        self.traces[action] += s_feats

        #Update weights
        self.weights[action] += self.alpha * td_error * self.traces[action]

        #Reset eligibility traces if episode ends
        if done:
            self.traces.fill(0)
            
    def update_alpha_epsilon(self): 
        self.epsilon = max(self.final_epsilon, self.epsilon*self.epsilon_decay)
        self.alpha = self.alpha*self.alpha_decay
        
    def policy(self, state): 
        state_feats = self.feature_encoder.encode(state)
        return self.Q(state_feats).argmax()
    
    def epsilon_greedy(self, state, epsilon=None):
        if epsilon is None: epsilon = self.epsilon
        if random.random()<epsilon:
            return self.env.action_space.sample()
        return self.policy(state)
       
        
    def train(self, n_episodes=200, max_steps_per_episode=200): 
        print(f'ep | eval | epsilon | alpha')
        for episode in range(n_episodes):
            done = False
            s, _ = self.env.reset()
            self.traces = np.zeros(self.shape)
            for i in range(max_steps_per_episode):
                
                action = self.epsilon_greedy(s)
                s_prime, reward, done, _, _ = self.env.step(action)
                self.update_transition(s, action, s_prime, reward, done)
                
                s = s_prime
                
                if done: break
                
            self.update_alpha_epsilon()

            if episode % 20 == 0:
                print(episode, self.evaluate(), self.epsilon, self.alpha)
                
    def evaluate(self, env=None, n_episodes=10, max_steps_per_episode=200): 
        if env is None:
            env = self.env
            
        rewards = []
        for episode in range(n_episodes):
            total_reward = 0
            done = False
            s, _ = env.reset()
            for i in range(max_steps_per_episode):
                action = self.policy(s)
                
                s_prime, reward, done, _, _ = env.step(action)
                
                total_reward += reward
                s = s_prime
                if done: break
            
            rewards.append(total_reward)
            
        return np.mean(rewards)

    def save(self, fname):
        with open(fname, 'wb') as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, fname):
        return pickle.load(open(fname,'rb'))
