-- À exécuter UNE SEULE FOIS avec psql, connecté en administrateur à postgres.
-- Ce fichier contient des commandes propres à psql (\password et \connect).
\set ON_ERROR_STOP on
CREATE ROLE enedis_app LOGIN;
\password enedis_app
CREATE DATABASE enedis OWNER enedis_app;
\connect enedis
CREATE EXTENSION IF NOT EXISTS postgis;
