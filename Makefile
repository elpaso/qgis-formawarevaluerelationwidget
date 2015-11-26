# Makefile for a PyQGIS plugin

all: compile

dist: package

install: copy2qgis

PY_FILES = FormAwareValueRelationWidget.py __init__.py
EXTRAS =
UI_FILES =
                                                                                                                                                                                                                                                                                                                                                                                                               RESOURCE_FILES =

compile: $(UI_FILES) $(RESOURCE_FILES)

%_rc.py : %.qrc
	pyrcc4 -o $@  $<

%.py : %.ui
	pyuic4 -o $@ $<


clean:
	find ./ -name "*.pyc" -exec rm -rf \{\} \;
	rm -f ../FormAwareValueRelationWidget.zip
	rm -f EXTRAS RESOURCE_FILES

package:
	cd .. && find FormAwareValueRelationWidget/  -print| grep -v Make | grep -v 'doc' | grep -v .pyc | grep -v zip | grep -v .git | zip FormAwareValueRelationWidget.zip -@

localrepo:
	cp ../FormAwareValueRelationWidget.zip ~/public_html/qgis/FormAwareValueRelationWidget.zip

copy2qgis: package
	unzip -o ../FormAwareValueRelationWidget.zip -d ~/.qgis/python/plugins

check test:
	@echo "Sorry: not implemented yet."
